"""
app/api/v1/applications.py
──────────────────────────
Fundi applies to / manages applications.
"""

from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import BaseModel, Field

from app.api.deps import ClientUser, CurrentSession, FundiUser
from app.core.supabase import get_user_client
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


def _application_write_http_error(exc: Exception, *, default_detail: str) -> HTTPException:
    if isinstance(exc, PostgrestAPIError):
        error_blob = " ".join(
            str(part or "")
            for part in (exc.code, exc.message, exc.details, exc.hint)
        ).lower()

        if exc.code == "23505" and ("uq_application" in error_blob or "job_id" in error_blob):
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already applied to this job",
            )

        if (
            exc.code in {"42501", "PGRST301", "PGRST302"}
            or "row-level security" in error_blob
            or "permission denied" in error_blob
        ):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this application.",
            )

    return HTTPException(status_code=500, detail=default_detail)


# ── Routes ───────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def apply_to_job(body: ApplyRequest, user: FundiUser, session: CurrentSession):
    """
    Fundi applies to a specific job.
    Enforces business rules: job must be open, exists, and not owned by the applicant.
    """
    client = get_user_client(session.access_token)

    try:
        # Verify job exists and is open
        result = client.table("jobs").select("id, title, status, client_id").eq("id", body.job_id).single().execute()
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

        insert_result = client.table("applications").insert(data).execute()
        application = insert_result.data[0]

        applicant_profile = None
        try:
            applicant_profile = (
                get_admin_client()
                .table("profiles")
                .select("full_name")
                .eq("id", user.user_id)
                .maybe_single()
                .execute()
                .data
            )
        except Exception as notification_lookup_error:
            logger.warning(
                "Could not resolve applicant name for notification",
                fundi_id=user.user_id,
                error=str(notification_lookup_error),
            )

        applicant_name = (applicant_profile or {}).get("full_name") or "A worker"
        await create_notification(
            user_id=job["client_id"],
            type_="application",
            title="New application received",
            body=f"{applicant_name} applied to {job['title']}.",
            action_url=f"/job-applicants.html?job={body.job_id}",
            metadata={
                "application_id": application["id"],
                "job_id": body.job_id,
                "fundi_id": user.user_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        
        logger.info("Application submitted", job_id=body.job_id, fundi_id=user.user_id)
        return application

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Application submission failed",
            job_id=body.job_id,
            fundi_id=user.user_id,
            error=str(exc),
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None) if hasattr(exc, "details") else None,
            hint=getattr(exc, "hint", None) if hasattr(exc, "hint") else None,
        )
        raise _application_write_http_error(
            exc,
            default_detail="Failed to submit application. Please try again.",
        )


@router.get("/mine")
async def my_applications(user: FundiUser, session: CurrentSession):
    """
    Returns all applications made by the current fundi, including job details.
    """
    client = get_user_client(session.access_token)
    try:
        result = (
            client.table("applications")
            .select(
                "*, "
                "jobs!job_id("
                "id, title, trade, county, area, budget_min, budget_max, status, client_id, "
                "profiles!client_id(full_name, avatar_url)"
                ")"
            )
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
    session: CurrentSession,
):
    """
    Allows a fundi to withdraw their application.
    Cannot withdraw if already hired or rejected.
    """
    client = get_user_client(session.access_token)
    
    try:
        app_result = (
            client.table("applications")
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

        update_result = (
            client.table("applications")
            .update({"status": body.status})
            .eq("id", application_id)
            .execute()
        )
        
        logger.info("Application updated", application_id=application_id, status=body.status)
        return update_result.data[0]
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Application update failed",
            application_id=application_id,
            fundi_id=user.user_id,
            error=str(exc),
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None) if hasattr(exc, "details") else None,
            hint=getattr(exc, "hint", None) if hasattr(exc, "hint") else None,
        )
        raise _application_write_http_error(exc, default_detail="Failed to update application.")


@router.patch("/{application_id}/client")
async def update_application_for_client(
    application_id: str,
    body: ClientUpdateApplicationRequest,
    user: ClientUser,
    session: CurrentSession,
):
    """
    Allows a client to manage an application on their own job.
    Clients can move applications between pending / shortlisted / rejected
    while the job is still open for review.
    """
    client = get_user_client(session.access_token)

    try:
        app_result = (
            client.table("applications")
            .select("id, job_id, fundi_id, status")
            .eq("id", application_id)
            .single()
            .execute()
        )
        app_data = app_result.data

        if not app_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

        job_result = (
            client.table("jobs")
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
            client.table("applications")
            .update({"status": body.status})
            .eq("id", application_id)
            .execute()
        )
        updated_application = update_result.data[0]

        if job_data["status"] == "open" and body.status in ("shortlisted", "rejected"):
            client.table("jobs").update({"status": "reviewing"}).eq("id", job_data["id"]).execute()

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
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None) if hasattr(exc, "details") else None,
            hint=getattr(exc, "hint", None) if hasattr(exc, "hint") else None,
        )
        raise _application_write_http_error(exc, default_detail="Failed to update application.")
