"""
app/api/v1/applications.py
──────────────────────────
Fundi applies to / manages applications.
"""

from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import ClientUser, FundiUser
from app.core.supabase import get_admin_client
from app.core.logging import get_logger
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    job_id:     str
    bid_amount: int | None = Field(None, ge=1)
    cover_note: str | None = Field(None, max_length=1000)


class UpdateApplicationRequest(BaseModel):
    status: Literal["withdrawn"]  # Only fundis can withdraw


class ClientUpdateApplicationRequest(BaseModel):
    status: Literal["pending", "shortlisted", "rejected"]


# ── Routes ───────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def apply_to_job(body: ApplyRequest, user: FundiUser):
    """
    Fundi applies to a specific job.
    Enforces business rules: job must be open, exists, and not owned by the applicant.
    """
    admin = get_admin_client()

    try:
        # Verify job exists and is open
        result = admin.table("jobs").select("id, status, client_id").eq("id", body.job_id).single().execute()
        job = result.data
        
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        
        if job["status"] != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Job is {job['status']} and no longer accepting applications"
            )
            
        if job["client_id"] == user.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Cannot apply to your own job"
            )

        data = {
            "job_id":     body.job_id,
            "fundi_id":   user.user_id,
            "bid_amount": body.bid_amount,
            "cover_note": body.cover_note,
            "status":     "pending",
        }

        insert_result = admin.table("applications").insert(data).execute()
        application = insert_result.data[0]
        
        logger.info("Application submitted", job_id=body.job_id, fundi_id=user.user_id)
        return application

    except HTTPException:
        raise
    except Exception as exc:
        # Check for unique constraint violation (already applied)
        error_msg = str(exc).lower()
        if "unique" in error_msg or "uq_application" in error_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied to this job")
        
        logger.error("Application submission failed", job_id=body.job_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to submit application. Please try again."
        )


@router.get("/mine")
async def my_applications(user: FundiUser):
    """
    Returns all applications made by the current fundi, including job details.
    """
    admin = get_admin_client()
    try:
        result = (
            admin.table("applications")
            .select("*, jobs!job_id(id, title, trade, county, area, budget_min, budget_max, status)")
            .eq("fundi_id", user.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"data": result.data}
    except Exception as exc:
        logger.error("Failed to fetch fundi applications", fundi_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch your applications.")


@router.patch("/{application_id}")
async def update_application(
    application_id: str,
    body: UpdateApplicationRequest,
    user: FundiUser,
):
    """
    Allows a fundi to withdraw their application.
    Cannot withdraw if already hired or rejected.
    """
    admin = get_admin_client()
    
    try:
        app_result = (
            admin.table("applications")
            .select("fundi_id, status")
            .eq("id", application_id)
            .single()
            .execute()
        )
        app_data = app_result.data
        
        if not app_data or app_data["fundi_id"] != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your application")
            
        if app_data["status"] in ("hired", "rejected"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Cannot withdraw a {app_data['status']} application"
            )

        update_result = admin.table("applications").update({"status": body.status}).eq("id", application_id).execute()
        
        logger.info("Application updated", application_id=application_id, status=body.status)
        return update_result.data[0]
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Application update failed", application_id=application_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update application.")


@router.patch("/{application_id}/client")
async def update_application_for_client(
    application_id: str,
    body: ClientUpdateApplicationRequest,
    user: ClientUser,
):
    """
    Allows a client to manage an application on their own job.
    Clients can move applications between pending / shortlisted / rejected
    while the job is still open for review.
    """
    admin = get_admin_client()

    try:
        app_result = (
            admin.table("applications")
            .select("id, job_id, fundi_id, status")
            .eq("id", application_id)
            .single()
            .execute()
        )
        app_data = app_result.data

        if not app_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

        job_result = (
            admin.table("jobs")
            .select("id, client_id, status, title")
            .eq("id", app_data["job_id"])
            .single()
            .execute()
        )
        job_data = job_result.data

        if not job_data or job_data["client_id"] != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your job")

        if job_data["status"] not in ("open", "reviewing"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job is {job_data['status']} and can no longer manage applicants",
            )

        if app_data["status"] in ("hired", "withdrawn"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update an application that is {app_data['status']}",
            )

        update_result = (
            admin.table("applications")
            .update({"status": body.status})
            .eq("id", application_id)
            .execute()
        )
        updated_application = update_result.data[0]

        if job_data["status"] == "open" and body.status in ("shortlisted", "rejected"):
            admin.table("jobs").update({"status": "reviewing"}).eq("id", job_data["id"]).execute()

        if body.status != app_data["status"]:
            titles = {
                "pending": "Application review reopened",
                "shortlisted": "You've been shortlisted ⭐",
                "rejected": "Application update",
            }
            bodies = {
                "pending": f"Your application for {job_data['title']} is back under review.",
                "shortlisted": f"Good news — you're shortlisted for {job_data['title']}.",
                "rejected": f"The client has passed on your application for {job_data['title']}.",
            }
            await create_notification(
                user_id=app_data["fundi_id"],
                type_="application_update",
                title=titles[body.status],
                body=bodies[body.status],
                action_url="/my-applications.html",
                metadata={
                    "application_id": application_id,
                    "job_id": job_data["id"],
                    "status": body.status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        logger.info(
            "Client updated application status",
            application_id=application_id,
            status=body.status,
            client_id=user.user_id,
        )
        return updated_application
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Client application update failed",
            application_id=application_id,
            client_id=user.user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to update application.")
