"""
app/api/v1/messages.py
──────────────────────
In-app chat endpoints.

GET  /v1/messages  → list messages (optionally scoped to a booking)
POST /v1/messages  → send a message
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()


class SendMessageRequest(BaseModel):
    booking_id: str
    recipient_id: str
    body: str = Field(..., min_length=1, max_length=2000)


def _verify_booking_participant(admin_client, booking_id: str, user_id: str) -> dict:
    booking = (
        admin_client.table("bookings")
        .select("id, client_id, fundi_id")
        .eq("id", booking_id)
        .maybe_single()
        .execute()
    )
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")

    participants = {booking.data["client_id"], booking.data["fundi_id"]}
    if user_id not in participants:
        raise HTTPException(status_code=403, detail="Not your booking")
    return booking.data


@router.get("/")
async def list_messages(
    user: CurrentUser,
    booking_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Lists chat messages for the current user.
    - with booking_id: returns that booking thread, oldest-first
    - without booking_id: returns the user's latest messages, newest-first
    """
    admin = get_admin_client()

    try:
        if booking_id:
            _verify_booking_participant(admin, booking_id, user.user_id)

            result = (
                admin.table("messages")
                .select("id, booking_id, sender_id, recipient_id, body, is_read, created_at")
                .eq("booking_id", booking_id)
                .order("created_at")
                .range(offset, offset + limit - 1)
                .execute()
            )

            # Mark any received messages as read when opening a thread.
            admin.table("messages").update({"is_read": True}).eq(
                "booking_id",
                booking_id,
            ).eq("recipient_id", user.user_id).eq("is_read", False).execute()
            rows = result.data or []
            return {"data": rows, "count": len(rows)}

        result = (
            admin.table("messages")
            .select("id, booking_id, sender_id, recipient_id, body, is_read, created_at")
            .or_(f"sender_id.eq.{user.user_id},recipient_id.eq.{user.user_id}")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        rows = result.data or []
        return {"data": rows, "count": len(rows)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Message listing failed", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch messages.")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def send_message(body: SendMessageRequest, user: CurrentUser):
    """
    Sends a message to the other party in a booking thread.
    """
    admin = get_admin_client()
    try:
        booking = _verify_booking_participant(admin, body.booking_id, user.user_id)
        participants = {booking["client_id"], booking["fundi_id"]}

        if body.recipient_id not in participants:
            raise HTTPException(status_code=400, detail="Recipient is not part of this booking")
        if body.recipient_id == user.user_id:
            raise HTTPException(status_code=400, detail="Cannot message yourself")

        payload = {
            "booking_id": body.booking_id,
            "sender_id": user.user_id,
            "recipient_id": body.recipient_id,
            "body": body.body.strip(),
            "is_read": False,
        }
        if not payload["body"]:
            raise HTTPException(status_code=400, detail="Message body cannot be blank")

        result = admin.table("messages").insert(payload).execute()
        message = result.data[0] if result.data else payload

        sender = (
            admin.table("profiles")
            .select("full_name")
            .eq("id", user.user_id)
            .maybe_single()
            .execute()
        )
        sender_name = sender.data["full_name"] if sender.data else "A user"

        await create_notification(
            user_id=body.recipient_id,
            type_="message",
            title=f"New message from {sender_name}",
            body=payload["body"][:120],
            action_url=f"/messages.html?booking={body.booking_id}",
        )

        return message
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Message send failed",
            booking_id=body.booking_id,
            sender_id=user.user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to send message.")
