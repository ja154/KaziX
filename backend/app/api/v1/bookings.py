"""
app/api/v1/bookings.py
──────────────────────
GET  /v1/bookings               → list bookings for the signed-in client or fundi
POST /v1/bookings/hire          → client hires a fundi (creates booking)
GET  /v1/bookings/{id}          → get booking detail
POST /v1/bookings/{id}/complete → client marks job complete, triggers escrow release
"""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import ClientUser, CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()

BOOKING_LIST_SELECT = (
    "id, job_id, application_id, client_id, fundi_id, agreed_amount, start_date, status, "
    "escrow_status, mpesa_receipt, created_at, updated_at, escrow_held_at, escrow_released_at, "
    "job:jobs!job_id(id, title, trade, county, area, status, created_at, updated_at), "
    "client_profile:profiles!client_id(id, full_name, phone, avatar_url, county, area), "
    "fundi_profile:profiles!fundi_id(id, full_name, phone, avatar_url, county, area), "
    "transactions(id, type, amount, mpesa_ref, status, created_at)"
)
FUNDI_DETAILS_FIELDS = (
    "trade",
    "rating_avg",
    "jobs_completed",
    "experience_years",
    "kyc_status",
    "is_available",
)
FUNDI_DETAILS_SELECT = "id, " + ", ".join(FUNDI_DETAILS_FIELDS)


def _serialize_fundi_details(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {field: row.get(field) for field in FUNDI_DETAILS_FIELDS}


def _with_default_fundi_details(booking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **dict(row),
            "fundi_details": dict(row).get("fundi_details"),
        }
        for row in booking_rows
    ]


def _attach_fundi_details(admin, booking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base_rows = _with_default_fundi_details(booking_rows)
    fundi_ids = sorted({str(row.get("fundi_id")) for row in booking_rows if row.get("fundi_id")})
    if not fundi_ids:
        return base_rows

    try:
        fundi_result = admin.table("fundi_profiles").select(FUNDI_DETAILS_SELECT).in_("id", fundi_ids).execute()
        fundi_details_by_id = {
            str(row["id"]): _serialize_fundi_details(row)
            for row in (fundi_result.data or [])
            if isinstance(row, dict) and row.get("id")
        }
    except Exception as exc:
        logger.warning(
            "Failed to enrich booking fundi details",
            fundi_count=len(fundi_ids),
            booking_count=len(base_rows),
            error=str(exc),
        )
        return base_rows

    enriched_rows: list[dict[str, Any]] = []
    for row in base_rows:
        enriched = dict(row)
        enriched["fundi_details"] = fundi_details_by_id.get(str(row.get("fundi_id"))) if row.get("fundi_id") else None
        enriched_rows.append(enriched)

    return enriched_rows


class HireRequest(BaseModel):
    application_id: str
    agreed_amount:  int = Field(..., ge=1)
    start_date:     str | None = None  # ISO date


@router.get("", include_in_schema=False)
@router.get("/")
async def list_bookings(
    user: CurrentUser,
    role: Literal["client", "fundi"] | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
):
    admin = get_admin_client()

    if user.role not in {"client", "fundi"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bookings can only be listed for signed-in client or fundi accounts.",
        )

    effective_role = role or user.role
    if effective_role != user.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view bookings for your own account role.",
        )

    try:
        query = (
            admin.table("bookings")
            .select(BOOKING_LIST_SELECT)
            .eq("client_id" if effective_role == "client" else "fundi_id", user.user_id)
        )

        normalized_status = str(status_filter or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_status and normalized_status != "all":
            if normalized_status == "active":
                query = query.in_("status", ["confirmed", "in_progress"])
            elif normalized_status == "awaiting_payment":
                query = query.eq("escrow_status", "pending")
            elif normalized_status in {"confirmed", "in_progress", "completed", "cancelled", "disputed"}:
                query = query.eq("status", normalized_status)
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Unsupported booking status filter.",
                )

        result = query.order("created_at", desc=True).execute()
        rows = _attach_fundi_details(admin, result.data or [])
        if not rows:
            logger.info(
                "Bookings list returned zero rows",
                user_id=user.user_id,
                role=effective_role,
                result_count=0,
            )
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to list bookings", user_id=user.user_id, role=effective_role, error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch bookings.")


@router.post("/hire", status_code=status.HTTP_201_CREATED)
async def hire_fundi(body: HireRequest, user: ClientUser):
    """
    Client hires a fundi:
    1. Validates application ownership
    2. Creates a booking row
    3. Updates application status → hired
    4. Updates job status → active
    5. Fires hired notification to fundi
    """
    admin = get_admin_client()

    try:
        # Fetch application + related job
        app_result = (
            admin.table("applications")
            .select("*, jobs!job_id(id, client_id, status, title)")
            .eq("id", body.application_id)
            .single()
            .execute()
        )
        if not app_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

        app_ = app_result.data
        job  = app_["jobs"]

        if job["client_id"] != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your job")
        if job["status"] not in ("open", "reviewing"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not available for hiring")
        if app_["status"] != "pending" and app_["status"] != "shortlisted":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot hire — application is {app_['status']}")

        # Create booking
        booking_data = {
            "job_id":          job["id"],
            "application_id":  body.application_id,
            "client_id":       user.user_id,
            "fundi_id":        app_["fundi_id"],
            "agreed_amount":   body.agreed_amount,
            "start_date":      body.start_date,
            "status":          "confirmed",
            "escrow_status":   "pending",
        }

        try:
            booking_result = admin.table("bookings").insert(booking_data).execute()
        except Exception as exc:
            if "uq_booking_application" in str(exc):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A booking already exists for this application")
            logger.error("Booking creation failed", error=str(exc))
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create booking")

        booking = booking_result.data[0]

        # Update application and job status
        admin.table("applications").update({"status": "hired"}).eq("id", body.application_id).execute()
        admin.table("jobs").update({"status": "active"}).eq("id", job["id"]).execute()

        # Notify fundi
        await create_notification(
            user_id=app_["fundi_id"],
            type_="hired",
            title="You've been hired! 🎉",
            body=f"You were hired for: {job['title']}. Check your bookings.",
            action_url="/worker-hires.html",
        )

        logger.info("Fundi hired", booking_id=booking["id"], fundi=app_["fundi_id"])
        return booking
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Hiring flow failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to complete hiring process.")


@router.get("/{booking_id}")
async def get_booking(booking_id: str, user: CurrentUser):
    admin = get_admin_client()
    try:
        result = (
            admin.table("bookings")
            .select(
                "*, "
                "jobs!job_id(title, trade, county, area), "
                "profiles!client_id(full_name, phone, avatar_url), "
                "profiles!fundi_id(full_name, phone, avatar_url), "
                "transactions(id, type, amount, mpesa_ref, status, created_at)"
            )
            .eq("id", booking_id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        b = dict(result.data)
        if b["client_id"] != user.user_id and b["fundi_id"] != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

        return _attach_fundi_details(admin, [b])[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch booking", booking_id=booking_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch booking.")


@router.post("/{booking_id}/complete")
async def confirm_job_complete(booking_id: str, user: ClientUser):
    """
    Client confirms job is done.
    Sets booking status → completed.
    M-Pesa escrow release is triggered separately by the mpesa router
    after payment confirmation.
    """
    admin = get_admin_client()
    try:
        booking = admin.table("bookings").select("*").eq("id", booking_id).single().execute()

        if not booking.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        b = booking.data

        if b["client_id"] != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the client can confirm completion")
        if b["status"] not in ("confirmed", "in_progress"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Booking is already {b['status']}")

        admin.table("bookings").update({
            "status": "completed",
        }).eq("id", booking_id).execute()

        # Notify fundi
        await create_notification(
            user_id=b["fundi_id"],
            type_="payment",
            title="Job confirmed complete ✅",
            body="The client has confirmed the job is done. Your M-Pesa payment is being released.",
            action_url="/worker-hires.html",
        )

        logger.info("Job confirmed complete", booking_id=booking_id, client=user.user_id)
        return {"success": True, "message": "Job marked complete. Escrow release initiated."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Job completion confirmation failed", booking_id=booking_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to confirm job completion.")
