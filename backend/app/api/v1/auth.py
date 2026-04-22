"""
app/api/v1/auth.py
──────────────────
Phone OTP authentication flow (Tasks 4 & 5).

POST /v1/auth/send-otp     → sends phone OTP or email sign-in link/code via Supabase
POST /v1/auth/verify-otp   → verifies OTP, creates profile if new user
POST /v1/auth/oauth/start  → returns Supabase OAuth authorize URL
POST /v1/auth/oauth/exchange → exchanges OAuth code for Supabase session
POST /v1/auth/profile      → completes registration (step 4 form data)
GET  /v1/auth/session      → returns current user + profile in one call
GET  /v1/auth/bootstrap    → returns profile completion state for OAuth/OTP sessions
"""

import secrets
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, status, Request
from gotrue.errors import AuthApiError, AuthRetryableError
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.deps import CurrentSession, CurrentUser
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.supabase import get_admin_client, get_anon_client, get_user_client
from supabase import create_client

logger = get_logger(__name__)
router = APIRouter()
settings = get_settings()

# Rate limiter
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
except ImportError:
    limiter = None

_OAUTH_STATE_TTL_SECONDS = 600
_OAUTH_STATE_STORE: dict[str, dict[str, str | float]] = {}


# ── Schemas ──────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    phone: str | None = Field(default=None, pattern=r"^\+254[0-9]{9}$", examples=["+254712345678"])
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    email_redirect_to: str | None = Field(default=None, min_length=1)
    should_create_user: bool = False

    @model_validator(mode="after")
    def validate_destination(self):
        if bool(self.phone) == bool(self.email):
            raise ValueError("Provide exactly one destination: phone or email.")
        if self.phone and self.email_redirect_to:
            raise ValueError("email_redirect_to is only supported for email sign-in.")
        if self.phone and self.should_create_user:
            raise ValueError("should_create_user is only supported for email sign-in.")
        return self


class VerifyOTPRequest(BaseModel):
    phone: str | None = Field(default=None, pattern=r"^\+254[0-9]{9}$")
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    token: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @model_validator(mode="after")
    def validate_destination(self):
        if bool(self.phone) == bool(self.email):
            raise ValueError("Provide exactly one destination: phone or email.")
        return self


class CreateProfileRequest(BaseModel):
    full_name: str      = Field(..., min_length=2, max_length=120)
    phone: str          = Field(..., pattern=r"^\+254[0-9]{9}$")
    email: str | None   = None
    county: str | None  = None
    area: str | None    = None
    role: Literal["client", "fundi"] = "client"
    mpesa_number: str | None = None
    preferred_language: Literal["en", "sw"] = "en"
    # Fundi-only fields
    trade: str | None           = None
    rate_min: int | None        = Field(None, ge=0)
    rate_max: int | None        = Field(None, ge=0)
    experience_years: int | None = Field(None, ge=0, le=60)
    bio: str | None             = None

    @field_validator("role")
    @classmethod
    def fundi_requires_trade(cls, role, info):
        # Full cross-field validation happens in the route handler
        return role


class OTPResponse(BaseModel):
    success: bool
    message: str


class EmailRegisterRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)


class EmailLoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)


class SessionResponse(BaseModel):
    user_id: str
    role: str
    phone: str
    full_name: str
    is_verified: bool


class OAuthStartRequest(BaseModel):
    provider: Literal["google", "apple", "github"]
    redirect_to: str = Field(..., min_length=1)
    scopes: str | None = None


class OAuthStartResponse(BaseModel):
    provider: str
    url: str
    state: str


class OAuthExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=8)
    redirect_to: str | None = None


class BootstrapResponse(BaseModel):
    is_new_user: bool
    redirect_to: str
    role: str
    profile: dict | None


def _resolve_profile_state(admin, user_id: str) -> tuple[dict | None, bool, str]:
    """
    Shared profile state resolver for OTP/OAuth flows.
    """
    existing = (
        admin.table("profiles")
        .select("id, role, full_name, phone, is_verified")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile = existing.data if existing else None
    is_new_user = profile is None or profile.get("full_name") == "User"
    role = profile.get("role") if profile else "client"
    redirect_to = "complete-registration" if is_new_user else f"{role}-dashboard"
    return profile, is_new_user, redirect_to


def _profile_write_http_error(exc: Exception, *, table_name: str) -> HTTPException:
    default_detail = (
        "Could not save fundi profile."
        if table_name == "fundi_profiles"
        else "Could not save profile. Please try again."
    )

    if isinstance(exc, PostgrestAPIError):
        error_blob = " ".join(
            str(part or "")
            for part in (exc.code, exc.message, exc.details, exc.hint)
        ).lower()

        if table_name == "profiles":
            if exc.code == "23505" and (
                "uq_profiles_phone" in error_blob or "key (phone)" in error_blob
            ):
                return HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "That phone number is already linked to another account. "
                        "Sign in instead or use a different number."
                    ),
                )
            if exc.code == "23503" and "auth.users" in error_blob:
                return HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Your verified session could not be matched to an account. Please verify your email again.",
                )
            if exc.code in {"23502", "23514", "22P02"} and (
                "phone" in error_blob or "mpesa_number" in error_blob
            ):
                return HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Enter a valid Kenyan phone number in +2547XXXXXXXX format.",
                )

        if table_name == "fundi_profiles":
            if exc.code == "23514" and "ck_fundi_rate_range" in error_blob:
                return HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Maximum rate must be greater than or equal to minimum rate.",
                )
            if exc.code == "23514" and "trade" in error_blob:
                return HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Please select a valid trade.",
                )
            if exc.code == "23514" and "experience_years" in error_blob:
                return HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Experience years must be between 0 and 60.",
                )

        if settings.app_env == "development":
            debug_detail = exc.details or exc.message or exc.code
            if debug_detail:
                return HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"{default_detail} ({debug_detail})",
                )

    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=default_detail,
    )


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(0, len(local) - 1)
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


def _auth_error_http_exception(
    exc: Exception,
    *,
    default_status: int,
    default_detail: str,
) -> HTTPException:
    message = getattr(exc, "message", None) or str(exc)
    code = getattr(exc, "code", None)
    status_code = getattr(exc, "status", None)
    blob = " ".join(
        str(part or "")
        for part in (message, code, status_code)
    ).lower()

    if "already" in blob and ("registered" in blob or "exists" in blob):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists. Sign in instead.",
        )
    if "invalid login credentials" in blob:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if "password" in blob and (
        "weak" in blob
        or "characters" in blob
        or "least" in blob
        or "length" in blob
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message or "Password must be at least 8 characters long.",
        )

    return HTTPException(
        status_code=default_status,
        detail=default_detail if settings.app_env == "production" else (message or default_detail),
    )


def _build_auth_payload(response, *, is_new_user: bool, redirect_to: str) -> dict:
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "token_type": "bearer",
        "expires_in": response.session.expires_in,
        "is_new_user": is_new_user,
        "redirect_to": redirect_to,
    }


def _cleanup_oauth_state(now_ts: float) -> None:
    expired = [
        state
        for state, payload in _OAUTH_STATE_STORE.items()
        if now_ts - float(payload.get("created_at", 0)) > _OAUTH_STATE_TTL_SECONDS
    ]
    for state in expired:
        _OAUTH_STATE_STORE.pop(state, None)


def _put_oauth_state(state: str, code_verifier: str) -> None:
    now_ts = time.time()
    _cleanup_oauth_state(now_ts)
    _OAUTH_STATE_STORE[state] = {
        "code_verifier": code_verifier,
        "created_at": now_ts,
    }


def _pop_oauth_code_verifier(state: str) -> str | None:
    now_ts = time.time()
    _cleanup_oauth_state(now_ts)
    payload = _OAUTH_STATE_STORE.pop(state, None)
    if not payload:
        return None
    return str(payload.get("code_verifier") or "")


def _is_valid_redirect_to(redirect_to: str | None) -> bool:
    """Validate redirect_to to prevent open redirect attacks."""
    if not redirect_to:
        return True  # None is allowed (will use default)
    # Whitelisted redirect targets from auth bootstrap
    valid = {
        "complete-registration",
        "client-dashboard",
        "fundi-dashboard",
        "admin-dashboard",
    }
    return redirect_to in valid


# ── Routes ───────────────────────────────────────────────────

@router.post("/email/register", status_code=201)
async def register_with_email(body: EmailRegisterRequest):
    """
    Creates a password-based email account and immediately signs the user in.
    This avoids OTP/magic-link setup and allows the frontend to proceed straight
    to profile completion.
    """
    admin = get_admin_client()
    try:
        created_user = admin.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                "email_confirm": True,
            }
        )
    except AuthApiError as exc:
        logger.warning(
            "Email registration rejected",
            email=_mask_email(body.email),
            code=getattr(exc, "code", None),
            error=str(exc),
        )
        raise _auth_error_http_exception(
            exc,
            default_status=status.HTTP_400_BAD_REQUEST,
            default_detail="Could not create account. Please try again.",
        )
    except Exception as exc:
        logger.error(
            "Email registration failed",
            email=_mask_email(body.email),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create account right now. Please try again.",
        )

    if not getattr(created_user, "user", None):
        logger.error(
            "Email registration returned no Supabase user",
            email=_mask_email(body.email),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create account right now. Please try again.",
        )

    logger.info(
        "Email registration created Supabase user",
        email=_mask_email(body.email),
        user_id=getattr(created_user.user, "id", None),
    )

    # Create a default profile row so /v1/profiles/me doesn't 404 for new users
    # Users will update this during the profile completion step
    user_id = getattr(created_user.user, "id", None)
    if user_id:
        try:
            default_profile = {
                "id": user_id,
                "role": "client",
                "full_name": "User",
                "phone": f"{body.email.split('@')[0]}@pending",  # Temporary placeholder
                "email": body.email,
                "preferred_language": "en",
            }
            admin.table("profiles").insert(default_profile).execute()
            logger.info(
                "Default profile created for new user",
                user_id=user_id,
                email=_mask_email(body.email),
            )
        except Exception as exc:
            # Non-blocking: log but don't fail signup if profile creation fails
            logger.warning(
                "Default profile creation failed during signup, continuing anyway",
                user_id=user_id,
                email=_mask_email(body.email),
                error=str(exc),
                code=getattr(exc, "code", None),
                details=getattr(exc, "details", None),
            )

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.sign_in_with_password(
            {
                "email": body.email,
                "password": body.password,
            }
        )
    except AuthApiError as exc:
        logger.error(
            "Email registration sign-in failed",
            email=_mask_email(body.email),
            code=getattr(exc, "code", None),
            error=str(exc),
        )
        raise _auth_error_http_exception(
            exc,
            default_status=status.HTTP_401_UNAUTHORIZED,
            default_detail="Account created, but sign-in failed. Please try signing in.",
        )
    except Exception as exc:
        logger.error(
            "Email registration sign-in unexpected failure",
            email=_mask_email(body.email),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account created, but sign-in failed. Please try signing in.",
        )

    if not response.session or not response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account was created but no session was returned.",
        )

    return _build_auth_payload(
        response,
        is_new_user=True,
        redirect_to="complete-registration",
    )


@router.post("/email/login", status_code=200)
async def login_with_email(body: EmailLoginRequest):
    """
    Signs an existing user in with email + password and returns the same
    session bootstrap payload used by the frontend auth flows.
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.sign_in_with_password(
            {
                "email": body.email,
                "password": body.password,
            }
        )
    except AuthApiError as exc:
        logger.warning(
            "Email login rejected",
            email=_mask_email(body.email),
            code=getattr(exc, "code", None),
            error=str(exc),
        )
        raise _auth_error_http_exception(
            exc,
            default_status=status.HTTP_401_UNAUTHORIZED,
            default_detail="Incorrect email or password.",
        )
    except Exception as exc:
        logger.error(
            "Email login failed",
            email=_mask_email(body.email),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not sign in right now. Please try again.",
        )

    if not response.session or not response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in did not return a session.",
        )

    admin = get_admin_client()
    try:
        _, is_new_user, redirect_to = _resolve_profile_state(admin, response.user.id)
    except Exception as exc:
        logger.error("Email login profile check failed", user_id=response.user.id, error=str(exc))
        is_new_user = True
        redirect_to = "complete-registration"

    return _build_auth_payload(
        response,
        is_new_user=is_new_user,
        redirect_to=redirect_to,
    )

@router.post("/send-otp", response_model=OTPResponse, status_code=200)
async def send_otp(body: SendOTPRequest):
    """
    Send a 6-digit OTP to phone or initiate passwordless email auth.
    Phone OTP uses SMS provider configured in Supabase.
    Email sends a magic link when email_redirect_to is provided.
    Otherwise, the email template decides whether users receive a code or link.
    Set should_create_user=True for registration flows so new email users
    can be created before profile completion.
    
    Handles rate limiting (429) with automatic retry and exponential backoff.
    """
    from app.services.otp import dispatch_otp_with_retry

    try:
        if body.phone:
            success, message = await dispatch_otp_with_retry(
                destination=body.phone,
                dispatch_type="phone",
            )
        else:  # email
            success, message = await dispatch_otp_with_retry(
                destination=str(body.email),
                dispatch_type="email",
                use_magic_link=bool(body.email_redirect_to),
                redirect_to=body.email_redirect_to,
                should_create_user=body.should_create_user,
            )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message,
            )

        return OTPResponse(success=True, message=message)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "OTP dispatch unexpected error",
            destination=body.phone[-4:] if body.phone else _mask_email(str(body.email)),
            error=str(exc),
        )
        detail = "Failed to send OTP. Please try again."
        if settings.app_env == "development":
            detail = f"Failed to send OTP: {str(exc)}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


@router.post("/verify-otp", status_code=200)
async def verify_otp(body: VerifyOTPRequest):
    """
    Verify OTP token.
    Returns Supabase session (access_token, refresh_token) + is_new_user flag.
    Frontend uses is_new_user to decide whether to show the profile completion form.
    """
    client = get_anon_client()
    response = None
    try:
        if body.phone:
            response = client.auth.verify_otp(
                {
                    "phone": body.phone,
                    "token": body.token,
                    "type": "sms",
                }
            )
        else:
            email = str(body.email)
            email_types = ("email", "signup", "magiclink")
            last_error = None
            for email_type in email_types:
                try:
                    response = client.auth.verify_otp(
                        {
                            "email": email,
                            "token": body.token,
                            "type": email_type,
                        }
                    )
                    break
                except Exception as exc:
                    last_error = exc

            if response is None:
                raise last_error or RuntimeError("Email OTP verification failed")
    except Exception as exc:
        logger.warning(
            "OTP verification failed",
            destination=body.phone[-4:] if body.phone else _mask_email(str(body.email)),
            error=str(exc),
        )
        detail = "Invalid or expired OTP."
        if settings.app_env == "development":
            detail = f"Invalid or expired OTP: {str(exc)}"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    if not response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OTP verification did not produce a session.",
        )

    user_id = response.user.id
    admin = get_admin_client()
    
    # Create a default profile row if this is a new user from OTP
    # This ensures /v1/profiles/me doesn't 404 for new OTP users
    if response.user:
        try:
            existing = (
                admin.table("profiles")
                .select("id")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            # Only create default profile if one doesn't already exist
            if not existing.data:
                destination = body.phone if body.phone else str(body.email)
                default_profile = {
                    "id": user_id,
                    "role": "client",
                    "full_name": "User",
                    "phone": body.phone or f"{str(body.email).split('@')[0]}@pending",
                    "email": body.email if body.email else None,
                    "preferred_language": "en",
                }
                admin.table("profiles").insert(default_profile).execute()
                logger.info(
                    "Default profile created for new OTP user",
                    user_id=user_id,
                    destination=destination[-4:] if body.phone else _mask_email(destination),
                )
        except Exception as exc:
            # Non-blocking: log but don't fail OTP verification if profile creation fails
            logger.warning(
                "Default profile creation failed during OTP verification, continuing anyway",
                user_id=user_id,
                error=str(exc),
                code=getattr(exc, "code", None),
            )

    try:
        _, is_new_user, redirect_to = _resolve_profile_state(admin, user_id)
    except Exception as exc:
        logger.error("Profile check failed", user_id=user_id, error=str(exc))
        is_new_user = True
        redirect_to = "complete-registration"

    return _build_auth_payload(response, is_new_user=is_new_user, redirect_to=redirect_to)


@router.post("/oauth/start", response_model=OAuthStartResponse, status_code=200)
async def start_oauth(body: OAuthStartRequest, request: Request):
    """
    Returns a Supabase OAuth authorization URL for the selected provider.
    Frontend should redirect the browser to the returned URL.
    Rate limited to 10 requests per minute per IP.
    """
    # Rate limiting check
    client_ip = request.client.host if request.client else "unknown"
    try:
        if hasattr(request.app, "state") and hasattr(request.app.state, "limiter"):
            limiter_instance = request.app.state.limiter
            rate_key = f"oauth_start:{client_ip}"
            if not limiter_instance.hit(rate_key, 10, 60):
                logger.warning("OAuth start rate limit exceeded", client_ip=client_ip)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many OAuth requests. Please wait before trying again.",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("Rate limiting check failed (non-blocking)", error=str(e))
    
    # Build an isolated auth client per request so we can safely capture
    # this login's PKCE code verifier without cross-user collisions.
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    state = secrets.token_urlsafe(24)

    options = {"redirect_to": body.redirect_to, "query_params": {"state": state}}
    if body.scopes:
        options["scopes"] = body.scopes

    try:
        response = client.auth.sign_in_with_oauth(
            {"provider": body.provider, "options": options}
        )

        storage = getattr(client.auth, "_storage", None)
        code_verifier = getattr(storage, "storage", {}).get(
            "supabase.auth.token-code-verifier"
        )
        if not code_verifier:
            raise RuntimeError("Missing PKCE code verifier for OAuth start")

        _put_oauth_state(state, str(code_verifier))
        logger.info(
            "OAuth start successful",
            provider=body.provider,
            state=state[:8],
        )
        return OAuthStartResponse(provider=response.provider, url=response.url, state=state)
    except AuthApiError as exc:
        logger.error(
            "OAuth start auth error",
            provider=body.provider,
            error=str(exc),
            code=getattr(exc, "code", None),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OAuth configuration error: {exc.message if hasattr(exc, 'message') else str(exc)}. Check Supabase OAuth provider settings.",
        )
    except Exception as exc:
        logger.error(
            "OAuth start failed",
            provider=body.provider,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to initialize OAuth login.",
        )


@router.post("/oauth/exchange", status_code=200)
async def exchange_oauth_code(body: OAuthExchangeRequest, request: Request):
    """
    Exchanges Supabase OAuth callback code for a session using the stored PKCE verifier.
    Validates redirect_to to prevent open redirect attacks.
    Rate limited to 5 requests per minute per IP.
    """
    # Rate limiting check
    client_ip = request.client.host if request.client else "unknown"
    try:
        if hasattr(request.app, "state") and hasattr(request.app.state, "limiter"):
            limiter_instance = request.app.state.limiter
            rate_key = f"oauth_exchange:{client_ip}"
            if not limiter_instance.hit(rate_key, 5, 60):
                logger.warning("OAuth exchange rate limit exceeded", client_ip=client_ip)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many token exchange attempts. Please try again later.",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("Rate limiting check failed (non-blocking)", error=str(e))
    code_verifier = _pop_oauth_code_verifier(body.state)
    if not code_verifier:
        logger.warning(
            "OAuth exchange: invalid or expired state",
            state=body.state[:8] if body.state else "missing",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OAuth state is invalid or expired. Please start login again.",
        )

    # Validate redirect_to to prevent open redirect
    if not _is_valid_redirect_to(body.redirect_to):
        logger.warning(
            "OAuth exchange: invalid redirect_to",
            state=body.state[:8],
            redirect_to=body.redirect_to,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid redirect target. Must be a recognized dashboard or flow.",
        )

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    exchange_payload = {
        "auth_code": body.code,
        "code_verifier": code_verifier,
    }
    if body.redirect_to:
        exchange_payload["redirect_to"] = body.redirect_to

    try:
        response = client.auth.exchange_code_for_session(exchange_payload)
    except AuthApiError as exc:
        logger.error(
            "OAuth exchange auth error",
            state=body.state[:8],
            error=str(exc),
            code=getattr(exc, "code", None),
            message=getattr(exc, "message", None),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth verification failed. Check that your authorization code is valid and not expired.",
        )
    except Exception as exc:
        logger.error(
            "OAuth exchange failed",
            state=body.state[:8],
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to complete OAuth login.",
        )

    if not response.session or not response.user:
        logger.error(
            "OAuth exchange: missing session or user",
            state=body.state[:8],
            has_session=bool(response.session),
            has_user=bool(response.user),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OAuth login did not return a session.",
        )

    user_id = response.user.id
    admin = get_admin_client()
    try:
        _, is_new_user, redirect_to = _resolve_profile_state(admin, user_id)
    except Exception as exc:
        logger.error("OAuth profile check failed", user_id=user_id, error=str(exc))
        is_new_user = True
        redirect_to = "complete-registration"

        return _build_auth_payload(response, is_new_user=is_new_user, redirect_to=redirect_to)


@router.post("/profile", status_code=201)
async def create_profile(body: CreateProfileRequest, user: CurrentSession):
    """
    Complete profile creation after OTP verification (register.html step 4).
    Idempotent — returns existing profile if one already exists.
    Creates a fundi_profiles row automatically when role == 'fundi'.
    """
    if body.role == "fundi" and not body.trade:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trade is required for fundi registration.",
        )
    if (
        body.role == "fundi"
        and body.rate_min is not None
        and body.rate_max is not None
        and body.rate_max < body.rate_min
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum rate must be greater than or equal to minimum rate.",
        )

    client = get_user_client(user.access_token)

    # Upsert profiles row (idempotent)
    profile_data = {
        "id":                 user.user_id,
        "role":               body.role,
        "full_name":          body.full_name,
        "phone":              body.phone,
        "email":              body.email,
        "county":             body.county,
        "area":               body.area,
        "mpesa_number":       body.mpesa_number or body.phone,
        "preferred_language": body.preferred_language,
    }

    try:
        profile_result = (
            client.table("profiles")
            .upsert(profile_data, on_conflict="id")
            .execute()
        )
    except Exception as exc:
        logger.error(
            "Profile upsert failed",
            user_id=user.user_id,
            error=str(exc),
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None),
            hint=getattr(exc, "hint", None),
        )
        raise _profile_write_http_error(exc, table_name="profiles")

    # Create fundi_profiles row if applicable
    if body.role == "fundi":
        fundi_data = {
            "id":               user.user_id,
            "trade":            body.trade,
            "bio":              body.bio,
            "rate_min":         body.rate_min,
            "rate_max":         body.rate_max,
            "experience_years": body.experience_years,
            "kyc_status":       "pending",
        }
        try:
            client.table("fundi_profiles").upsert(fundi_data, on_conflict="id").execute()
        except Exception as exc:
            logger.error(
                "Fundi profile upsert failed",
                user_id=user.user_id,
                error=str(exc),
                code=getattr(exc, "code", None),
                details=getattr(exc, "details", None),
                hint=getattr(exc, "hint", None),
            )
            raise _profile_write_http_error(exc, table_name="fundi_profiles")

    logger.info("Profile created", user_id=user.user_id, role=body.role)
    return {"success": True, "profile": profile_result.data[0] if profile_result.data else {}}


@router.get("/session", response_model=SessionResponse)
async def get_session(user: CurrentUser):
    """
    Returns the current user's profile in a single call.
    Import and call from every authenticated page on load.
    """
    admin = get_admin_client()
    try:
        result = (
            admin.table("profiles")
            .select("id, role, phone, full_name, is_verified")
            .eq("id", user.user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        p = result.data
        return SessionResponse(
            user_id=p["id"],
            role=p["role"],
            phone=p["phone"],
            full_name=p["full_name"],
            is_verified=p["is_verified"],
        )
    except Exception as exc:
        logger.error("Session fetch failed", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch session data.")


@router.get("/bootstrap", response_model=BootstrapResponse, status_code=200)
async def bootstrap_auth(user: CurrentSession):
    """
    Returns profile completion state for any authenticated Supabase session
    (OTP or OAuth), allowing frontend to route users after login.
    """
    admin = get_admin_client()
    try:
        profile, is_new_user, redirect_to = _resolve_profile_state(admin, user.user_id)
        role = profile.get("role") if profile else "client"
        return BootstrapResponse(
            is_new_user=is_new_user,
            redirect_to=redirect_to,
            role=role,
            profile=profile,
        )
    except Exception as exc:
        logger.error("Auth bootstrap failed", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to bootstrap auth state.")


@router.post("/oauth/refresh", status_code=200)
async def refresh_oauth_token(body: dict):
    """
    Refresh expired access token using refresh token.
    Frontend calls this before access_token expires to get a new one.
    """
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing refresh_token",
        )

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.refresh_session(refresh_token)
        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token invalid or expired. Please sign in again.",
            )
        logger.info("Token refreshed")
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "token_type": "bearer",
            "expires_in": response.session.expires_in,
        }
    except AuthApiError as exc:
        logger.warning(
            "Token refresh auth error",
            error=str(exc),
            code=getattr(exc, "code", None),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalid or expired. Please sign in again.",
        )
    except Exception as exc:
        logger.error("Token refresh failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token refresh service unavailable. Please try again.",
        )


@router.post("/logout", status_code=200)
async def logout(session: CurrentSession):
    """
    Logs out the user by signing them out from Supabase.
    Frontend should clear localStorage tokens and redirect to login.
    """
    try:
        get_anon_client().auth.admin.sign_out(session.access_token)
        logger.info("User logged out", user_id=session.user_id)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        logger.warning("Logout failed", user_id=session.user_id, error=str(exc))
        # Still return success even if sign_out fails, frontend should clear tokens
        return {"success": True, "message": "Logged out successfully"}
