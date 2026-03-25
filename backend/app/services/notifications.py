"""
app/services/notifications.py
──────────────────────────────
Internal service for creating notifications.
Always uses the admin client (service role) — inserts bypass RLS.
Import and call from any router or background task.
"""

from app.core.supabase import get_admin_client
from app.core.logging import get_logger

logger = get_logger(__name__)

VALID_TYPES = frozenset({
    "new_application", "hired", "message", "payment",
    "dispute", "review", "review_request", "kyc_update", "job_alert",
})


async def create_notification(
    user_id: str,
    type_: str,
    title: str,
    body: str,
    action_url: str | None = None,
) -> dict | None:
    """
    Inserts a notification row. Supabase Realtime will broadcast the
    INSERT to any subscriber filtering on user_id (Task 7).

    Returns the created row or None on failure (non-fatal — never raise).
    """
    if type_ not in VALID_TYPES:
        logger.warning("Unknown notification type", type_=type_)
        return None

    admin = get_admin_client()
    data = {
        "user_id":    user_id,
        "type":       type_,
        "title":      title,
        "body":       body,
        "action_url": action_url,
        "is_read":    False,
    }

    try:
        result = admin.table("notifications").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as exc:
        # Notifications are best-effort — log and swallow
        logger.error("Notification insert failed", user=user_id, error=str(exc))
        return None


async def notify_new_application(job_title: str, client_id: str, fundi_name: str, job_id: str):
    await create_notification(
        user_id=client_id,
        type_="new_application",
        title=f"New application on: {job_title}",
        body=f"{fundi_name} applied to your job. Review their profile and bid.",
        action_url=f"/job-applicants.html?job={job_id}",
    )


async def notify_new_message(recipient_id: str, sender_name: str, preview: str, booking_id: str):
    await create_notification(
        user_id=recipient_id,
        type_="message",
        title=f"New message from {sender_name}",
        body=preview[:120],
        action_url=f"/messages.html?booking={booking_id}",
    )


async def notify_payment_released(fundi_id: str, amount: int, booking_id: str):
    await create_notification(
        user_id=fundi_id,
        type_="payment",
        title="Payment released 💸",
        body=f"KES {amount:,} has been sent to your M-Pesa. Check your phone.",
        action_url=f"/worker-hires.html",
    )


async def notify_dispute_opened(fundi_id: str, booking_id: str):
    await create_notification(
        user_id=fundi_id,
        type_="dispute",
        title="Dispute opened on your booking",
        body="The client has raised a dispute. KaziX admin will review within 24 hours.",
        action_url="/worker-hires.html",
    )
