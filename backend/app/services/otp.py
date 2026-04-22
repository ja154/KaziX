"""
app/services/otp.py
───────────────────
OTP dispatch service with rate limiting, retry logic, and queue management.
Handles exponential backoff for Supabase rate limits (429 Too Many Requests).
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Literal

from gotrue.errors import AuthApiError, AuthRetryableError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.supabase import get_anon_client

logger = get_logger(__name__)
settings = get_settings()


# ── Configuration ────────────────────────────────────────────────

@dataclass
class OTPRetryConfig:
    """Configuration for OTP retry behavior."""
    max_retries: int = 3
    initial_backoff_ms: int = 100  # Start with 100ms
    max_backoff_ms: int = 5000     # Cap at 5 seconds
    backoff_multiplier: float = 2.0
    jitter_enabled: bool = True    # Add randomization to prevent thundering herd


# ── Queue Management ────────────────────────────────────────────

@dataclass
class OTPQueueItem:
    """Represents a queued OTP dispatch request."""
    destination: str  # phone or email
    dispatch_fn: Callable
    retry_count: int = 0
    next_retry_at: float = 0.0


class OTPQueue:
    """
    Thread-safe queue for OTP dispatch with exponential backoff.
    Handles rate limiting by queuing retries with delays.
    """

    def __init__(self, config: OTPRetryConfig | None = None):
        self.config = config or OTPRetryConfig()
        self.queue: list[OTPQueueItem] = []
        self._lock = asyncio.Lock()
        self._processing = False

    async def enqueue(
        self,
        destination: str,
        dispatch_fn: Callable,
    ) -> bool:
        """
        Enqueue an OTP dispatch request.
        Returns True if successfully queued, False if max retries exceeded.
        """
        async with self._lock:
            item = OTPQueueItem(
                destination=destination,
                dispatch_fn=dispatch_fn,
                retry_count=0,
                next_retry_at=time.time(),
            )
            self.queue.append(item)
            logger.debug("OTP queued", destination=destination, queue_size=len(self.queue))
            return True

    async def process(self) -> None:
        """
        Process queued OTP requests with exponential backoff.
        Called periodically by background task or on-demand.
        """
        if self._processing:
            return
        self._processing = True

        try:
            while True:
                async with self._lock:
                    if not self.queue:
                        break

                    # Find the next item that's ready to retry
                    now = time.time()
                    ready_idx = None
                    for idx, item in enumerate(self.queue):
                        if item.next_retry_at <= now:
                            ready_idx = idx
                            break

                    if ready_idx is None:
                        break  # No items ready yet

                    item = self.queue.pop(ready_idx)

                try:
                    await item.dispatch_fn()
                    logger.info(
                        "OTP dispatch succeeded after retry",
                        destination=item.destination,
                        retry_count=item.retry_count,
                    )
                except (AuthApiError, AuthRetryableError) as exc:
                    # Check if it's a rate limit error (429)
                    api_status = getattr(exc, "status", None)
                    is_rate_limit = api_status == 429
                    is_retryable = isinstance(exc, AuthRetryableError) or is_rate_limit

                    if is_retryable and item.retry_count < self.config.max_retries:
                        # Calculate exponential backoff with optional jitter
                        backoff_ms = min(
                            self.config.initial_backoff_ms
                            * (self.config.backoff_multiplier ** item.retry_count),
                            self.config.max_backoff_ms,
                        )

                        if self.config.jitter_enabled:
                            import random
                            backoff_ms *= random.uniform(0.8, 1.2)

                        item.retry_count += 1
                        item.next_retry_at = time.time() + (backoff_ms / 1000.0)

                        async with self._lock:
                            self.queue.append(item)

                        logger.warning(
                            "OTP requeued after rate limit/transient error",
                            destination=item.destination,
                            retry_count=item.retry_count,
                            backoff_ms=backoff_ms,
                            error_code=api_status,
                        )
                    else:
                        # Exceeded retries or non-retryable error
                        logger.error(
                            "OTP dispatch failed, max retries exceeded",
                            destination=item.destination,
                            retry_count=item.retry_count,
                            error=str(exc),
                        )
                except Exception as exc:
                    logger.error(
                        "OTP dispatch unexpected error",
                        destination=item.destination,
                        error=str(exc),
                    )

        finally:
            self._processing = False


# ── Global Queue Instance ────────────────────────────────────

_otp_queue = OTPQueue()


async def get_otp_queue() -> OTPQueue:
    """Get the global OTP queue instance."""
    return _otp_queue


# ── Dispatch Functions ───────────────────────────────────────

def _mask_email(email: str) -> str:
    """Mask email for logging."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(0, len(local) - 1)
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


async def send_phone_otp(phone: str) -> None:
    """
    Send phone OTP via Supabase.
    May raise AuthApiError, AuthRetryableError, or other exceptions.
    """
    client = get_anon_client()
    client.auth.sign_in_with_otp({"phone": phone})
    logger.info("OTP dispatched", channel="phone", phone=phone[-4:])


async def send_email_otp(
    email: str,
    use_magic_link: bool = False,
    redirect_to: str | None = None,
    should_create_user: bool = False,
) -> None:
    """
    Send email OTP or magic link via Supabase.
    May raise AuthApiError, AuthRetryableError, or other exceptions.
    """
    client = get_anon_client()
    options = {"should_create_user": should_create_user}
    if use_magic_link and redirect_to:
        options["email_redirect_to"] = redirect_to

    client.auth.sign_in_with_otp(
        {
            "email": email,
            "options": options,
        }
    )

    delivery = "magic_link" if use_magic_link else "otp"
    logger.info(
        "OTP dispatched",
        channel="email",
        delivery=delivery,
        email=_mask_email(email),
    )


async def dispatch_otp_with_retry(
    destination: str,
    dispatch_type: Literal["phone", "email"],
    use_magic_link: bool = False,
    redirect_to: str | None = None,
    should_create_user: bool = False,
) -> tuple[bool, str]:
    """
    Dispatch OTP with automatic retry on rate limits.

    Returns:
        (success: bool, message: str)
        - success=True: OTP sent successfully
        - success=False: Failed (check message for details)
    """
    queue = await get_otp_queue()

    try:
        if dispatch_type == "phone":
            dispatch_fn = lambda: send_phone_otp(destination)
        else:  # email
            dispatch_fn = lambda: send_email_otp(
                destination,
                use_magic_link=use_magic_link,
                redirect_to=redirect_to,
                should_create_user=should_create_user,
            )

        # Try immediate dispatch first
        try:
            await dispatch_fn()
            if dispatch_type == "phone":
                return True, "OTP sent successfully"
            elif use_magic_link:
                return True, "Magic link sent successfully"
            else:
                return True, "Verification code sent successfully"

        except (AuthApiError, AuthRetryableError) as exc:
            api_status = getattr(exc, "status", None)
            is_rate_limit = api_status == 429
            is_retryable = isinstance(exc, AuthRetryableError) or is_rate_limit

            if not is_retryable:
                # Non-retryable error, fail immediately
                logger.warning(
                    "OTP dispatch rejected",
                    destination=destination[-4:] if destination else "unknown",
                    status=api_status,
                    error=str(exc),
                )
                raise

            # Retryable error (rate limit or transient), queue it
            logger.info(
                "OTP dispatch rate limited, queuing for retry",
                destination=destination[-4:] if destination else "unknown",
            )
            await queue.enqueue(destination, dispatch_fn)

            # Return provisional success; user will get OTP on next retry
            if dispatch_type == "phone":
                return True, "OTP sending queued, will retry shortly"
            elif use_magic_link:
                return True, "Magic link queued, will resend shortly"
            else:
                return True, "Verification code queued, will resend shortly"

    except AuthApiError as exc:
        logger.warning(
            "OTP dispatch rejected by Supabase",
            destination=destination[-4:] if destination else "unknown",
            status=getattr(exc, "status", None),
            code=getattr(exc, "code", None),
            error=str(exc),
        )
        detail = f"Failed to send OTP: {str(exc)}" if settings.app_env == "development" else "Failed to send OTP"
        return False, detail

    except AuthRetryableError as exc:
        logger.error("OTP dispatch retryable failure", error=str(exc))
        detail = f"Failed to send OTP: {str(exc)}" if settings.app_env == "development" else "Failed to send OTP"
        return False, detail

    except Exception as exc:
        logger.error("OTP dispatch unexpected error", error=str(exc))
        detail = f"Failed to send OTP: {str(exc)}" if settings.app_env == "development" else "Failed to send OTP"
        return False, detail


# ── Background Processing ────────────────────────────────────

async def process_otp_queue_periodic() -> None:
    """
    Background task to process queued OTP requests periodically.
    Call this from FastAPI lifespan or a background task scheduler.
    """
    queue = await get_otp_queue()
    await queue.process()
