"""
app/api/v1/admin.py
───────────────────
Admin-only endpoints. All routes require role=admin.

GET  /v1/admin/kyc/queue          → pending KYC submissions
POST /v1/admin/kyc/{fundi_id}     → approve / reject / request resubmission
GET  /v1/admin/users              → list all users
POST /v1/admin/users/{id}/suspend → suspend / unsuspend account
GET  /v1/admin/disputes           → disputes queue
PATCH /v1/admin/disputes/{id}     → resolve a dispute
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import AdminUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()


# ── KYC ──────────────────────────────────────────────────────

class KYCDecisionRequest(BaseModel):
    decision:       Literal["approved", "rejected", "resubmission_requested"]
    admin_notes:    str | None = None


@router.get("/kyc/queue")
async def kyc_queue(_: AdminUser, status: str = Query("pending")):
    """
    Lists fundi profiles awaiting KYC review.
    """
    client = get_admin_client()
    try:
        result = (
            client.table("fundi_profiles")
            .select(
                "id, trade, kyc_status, kyc_reviewed_at, created_at, "
                "profiles!id(full_name, phone, county)"
            )
            .eq("kyc_status", status)
            .order("created_at")
            .execute()
        )
        return {"data": result.data}
    except Exception as exc:
        logger.error("Failed to fetch KYC queue", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch KYC queue.")


@router.post("/kyc/{fundi_id}")
async def review_kyc(fundi_id: str, body: KYCDecisionRequest, admin_user: AdminUser):
    """
    Approve or reject a fundi's KYC submission.
    On approval, marks the main profile as verified.
    """
    client = get_admin_client()

    update = {
        "kyc_status":       body.decision,
        "kyc_reviewed_at":  datetime.utcnow().isoformat(),
        "kyc_reviewer_id":  admin_user.user_id,
    }
    
    try:
        client.table("fundi_profiles").update(update).eq("id", fundi_id).execute()

        # Mark profile verified on approval
        if body.decision == "approved":
            client.table("profiles").update({"is_verified": True}).eq("id", fundi_id).execute()

        titles = {
            "approved":                 "ID Verified ✅",
            "rejected":                 "ID Verification Failed",
            "resubmission_requested":   "Please Resubmit Your ID",
        }
        bodies = {
            "approved":                 "Congratulations! Your identity has been verified. You can now receive bookings.",
            "rejected":                 f"Your ID verification was rejected. {body.admin_notes or ''}",
            "resubmission_requested":   f"Please re-upload your ID documents. {body.admin_notes or ''}",
        }
        
        await create_notification(
            user_id=fundi_id,
            type_="kyc_update",
            title=titles[body.decision],
            body=bodies[body.decision],
            action_url="/verify-id.html",
        )

        logger.info("KYC reviewed", fundi=fundi_id, decision=body.decision, reviewer=admin_user.user_id)
        return {"success": True, "decision": body.decision}
    except Exception as exc:
        logger.error("KYC review processing failed", fundi_id=fundi_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to process KYC review.")


# ── Users ─────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    _: AdminUser,
    role:   str | None = Query(None),
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Administrative user listing with pagination and role filtering.
    """
    client = get_admin_client()
    try:
        q = (
            client.table("profiles")
            .select("id, full_name, phone, county, role, is_verified, is_suspended, created_at")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if role:
            q = q.eq("role", role)
        result = q.execute()
        return {"data": result.data}
    except Exception as exc:
        logger.error("User listing failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list users.")


class SuspendRequest(BaseModel):
    suspend: bool


@router.post("/users/{user_id}/suspend")
async def toggle_suspend(user_id: str, body: SuspendRequest, admin: AdminUser):
    """
    Suspend or unsuspend a user account.
    Suspended users are blocked by the get_current_user dependency.
    """
    client = get_admin_client()
    try:
        client.table("profiles").update({"is_suspended": body.suspend}).eq("id", user_id).execute()
        action = "suspended" if body.suspend else "unsuspended"
        logger.info("User suspension toggled", user=user_id, action=action, by=admin.user_id)
        return {"success": True, "action": action}
    except Exception as exc:
        logger.error("Suspension toggle failed", user_id=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to toggle user suspension.")


# ── Disputes ──────────────────────────────────────────────────

@router.get("/disputes")
async def list_disputes(_: AdminUser, status: str = Query("open")):
    """
    Lists active or resolved disputes.
    """
    client = get_admin_client()
    try:
        result = (
            client.table("disputes")
            .select(
                "*, "
                "bookings!booking_id(agreed_amount, escrow_status, client_id, fundi_id), "
                "profiles!raised_by(full_name, phone)"
            )
            .eq("status", status)
            .order("created_at")
            .execute()
        )
        return {"data": result.data}
    except Exception as exc:
        logger.error("Dispute listing failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch disputes.")


class ResolveDisputeRequest(BaseModel):
    resolution: Literal["resolved_client", "resolved_fundi", "withdrawn"]
    admin_notes: str
    release_to:  Literal["client", "fundi"] | None = None


@router.patch("/disputes/{dispute_id}")
async def resolve_dispute(dispute_id: str, body: ResolveDisputeRequest, admin_user: AdminUser):
    """
    Resolves a dispute and optionally triggers an escrow release or refund.
    """
    client = get_admin_client()

    try:
        dispute_result = client.table("disputes").select("booking_id").eq("id", dispute_id).single().execute()
        if not dispute_result.data:
            raise HTTPException(status_code=404, detail="Dispute not found")

        # Update dispute
        client.table("disputes").update({
            "status":       body.resolution,
            "admin_notes":  body.admin_notes,
            "resolved_by":  admin_user.user_id,
            "resolved_at":  datetime.utcnow().isoformat(),
        }).eq("id", dispute_id).execute()

        # Fetch booking details for notification
        booking_result = (
            client.table("bookings")
            .select("client_id, fundi_id, jobs!job_id(title)")
            .eq("id", dispute_result.data["booking_id"])
            .single()
            .execute()
        )
        if booking_result.data:
            bk = booking_result.data
            job_title = bk["jobs"]["title"] if bk.get("jobs") else "Job"
            
            # Notify both parties
            import asyncio
            for uid in [bk["client_id"], bk["fundi_id"]]:
                asyncio.create_task(create_notification(
                    user_id=uid,
                    type_="dispute",
                    title="Dispute Resolved ✅",
                    body=f"The dispute on '{job_title}' has been resolved: {body.resolution}.",
                    action_url="/dispute.html" if uid == bk["client_id"] else "/worker-hires.html",
                ))

        # Update booking escrow if a release direction was specified
        if body.release_to:
            escrow_status = "released" if body.release_to == "fundi" else "refunded"
            client.table("bookings").update({
                "escrow_status":       escrow_status,
                "escrow_released_at":  datetime.utcnow().isoformat(),
                "status":              "completed",
            }).eq("id", dispute_result.data["booking_id"]).execute()

        logger.info("Dispute resolved", dispute=dispute_id, resolution=body.resolution)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Dispute resolution failed", dispute_id=dispute_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to resolve dispute.")
