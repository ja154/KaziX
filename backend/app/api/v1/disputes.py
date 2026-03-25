"""
app/api/v1/disputes.py
──────────────────────
Client dispute creation endpoint.

POST /v1/disputes  → client raises a dispute on their booking
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import ClientUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()


class CreateDisputeRequest(BaseModel):
    booking_id: str
    reason: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=20, max_length=4000)
    desired_resolution: str | None = Field(None, max_length=200)
    amount_disputed: int | None = Field(None, ge=0)
    evidence_urls: list[str] = Field(default_factory=list, max_length=10)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def raise_dispute(body: CreateDisputeRequest, user: ClientUser):
    """
    Creates an open dispute for a booking owned by the calling client.
    """
    admin = get_admin_client()
    try:
        booking = (
            admin.table("bookings")
            .select("id, client_id, fundi_id, status, escrow_status")
            .eq("id", body.booking_id)
            .maybe_single()
            .execute()
        )
        if not booking.data:
            raise HTTPException(status_code=404, detail="Booking not found")

        b = booking.data
        if b["client_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Not your booking")
        if b["status"] in {"cancelled"}:
            raise HTTPException(status_code=400, detail="Cannot dispute a cancelled booking")

        existing_open = (
            admin.table("disputes")
            .select("id")
            .eq("booking_id", body.booking_id)
            .eq("status", "open")
            .maybe_single()
            .execute()
        )
        if existing_open.data:
            raise HTTPException(status_code=409, detail="An open dispute already exists for this booking")

        payload = {
            "booking_id": body.booking_id,
            "raised_by": user.user_id,
            "reason": body.reason,
            "description": body.description,
            "desired_resolution": body.desired_resolution,
            "amount_disputed": body.amount_disputed,
            "evidence_urls": body.evidence_urls,
            "status": "open",
        }
        result = admin.table("disputes").insert(payload).execute()
        dispute = result.data[0] if result.data else payload

        # Freeze escrow in dispute flow unless it has already been finalized.
        if b["escrow_status"] in {"pending", "held"}:
            admin.table("bookings").update({"escrow_status": "disputed"}).eq(
                "id",
                body.booking_id,
            ).execute()

        await create_notification(
            user_id=b["fundi_id"],
            type_="dispute",
            title="Dispute opened on your booking",
            body="A client opened a dispute. KaziX admin will review and contact both parties.",
            action_url="/worker-hires.html",
        )

        return dispute
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Dispute creation failed",
            booking_id=body.booking_id,
            client_id=user.user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to raise dispute.")
