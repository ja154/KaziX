"""
app/api/v1/jobs.py
──────────────────
CRUD for jobs + application listing.

GET    /v1/jobs            → list open jobs (filterable)
GET    /v1/jobs/mine       → client views their own jobs
POST   /v1/jobs            → client creates a job
GET    /v1/jobs/{id}       → get one job
PATCH  /v1/jobs/{id}       → client updates their job
DELETE /v1/jobs/{id}       → client cancels/deletes their job
GET    /v1/jobs/{id}/applications → client views applicants
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import BaseModel, Field

from app.api.deps import ClientUser, CurrentSession, CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_anon_client, get_user_client

logger = get_logger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────

TRADE_TYPES = Literal[
    "plumber","electrician","mason","mama_fua","carpenter",
    "painter","roofer","gardener","driver_mover","security","other"
]

class CreateJobRequest(BaseModel):
    title:              str             = Field(..., min_length=5, max_length=200)
    description:        str             = Field(..., min_length=20)
    trade:              TRADE_TYPES
    county:             str
    area:               str
    street:             str | None      = None
    budget_min:         int | None      = Field(None, ge=0)
    budget_max:         int | None      = Field(None, ge=0)
    payment_type:       Literal["fixed","hourly","daily","negotiable"] = "negotiable"
    urgency:            Literal["flexible","urgent"] = "flexible"
    preferred_date:     str | None      = None   # ISO date string
    preferred_time:     str | None      = None
    materials_provided: bool            = False


class UpdateJobRequest(BaseModel):
    title:              str | None      = Field(None, min_length=5, max_length=200)
    description:        str | None      = Field(None, min_length=20)
    budget_min:         int | None      = Field(None, ge=0)
    budget_max:         int | None      = Field(None, ge=0)
    urgency:            Literal["flexible","urgent"] | None = None
    preferred_date:     str | None      = None
    status:             Literal["open","cancelled"] | None = None


def _job_write_http_error(exc: Exception, *, default_detail: str) -> HTTPException:
    if isinstance(exc, PostgrestAPIError):
        error_blob = " ".join(
            str(part or "")
            for part in (exc.code, exc.message, exc.details, exc.hint)
        ).lower()

        if (
            exc.code in {"42501", "PGRST301", "PGRST302"}
            or "row-level security" in error_blob
            or "permission denied" in error_blob
        ):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this job.",
            )

        if exc.code == "23514" and "ck_jobs_budget_range" in error_blob:
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Maximum budget must be greater than or equal to minimum budget.",
            )

        if exc.code in {"22007", "22P02"} and "preferred_date" in error_blob:
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Please choose a valid preferred date.",
            )

        if exc.code in {"23514", "22P02"} and "trade" in error_blob:
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Please select a valid trade.",
            )

    return HTTPException(status_code=500, detail=default_detail)


# ── Routes ───────────────────────────────────────────────────

@router.get("/")
async def list_jobs(
    trade:   str | None = Query(None),
    county:  str | None = Query(None),
    urgency: str | None = Query(None),
    limit:   int        = Query(20, ge=1, le=100),
    offset:  int        = Query(0, ge=0),
):
    """Public — lists open jobs with optional filters."""
    client = get_anon_client()
    try:
        q = (
            client.table("jobs")
            .select(
                "id, title, description, trade, county, area, budget_min, budget_max, "
                "payment_type, urgency, preferred_date, materials_provided, "
                "status, expires_at, created_at, "
                "profiles!client_id(full_name, avatar_url)"
            )
            .eq("status", "open")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if trade:
            q = q.eq("trade", trade)
        if county:
            q = q.eq("county", county)
        if urgency:
            q = q.eq("urgency", urgency)

        result = q.execute()
        return {"data": result.data, "count": len(result.data)}
    except Exception as exc:
        logger.error("Job listing failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch jobs.")


@router.get("/mine")
async def list_my_jobs(user: ClientUser, session: CurrentSession):
    """Client-only — list jobs posted by the authenticated user."""
    client = get_user_client(session.access_token)
    try:
        result = (
            client.table("jobs")
            .select(
                "id, title, description, trade, county, area, street, budget_min, "
                "budget_max, payment_type, urgency, preferred_date, preferred_time, "
                "materials_provided, status, expires_at, created_at, updated_at"
            )
            .eq("client_id", user.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"data": result.data, "count": len(result.data)}
    except Exception as exc:
        logger.error("Failed to fetch client jobs", client_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch your jobs.")


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Public — get full job detail."""
    client = get_anon_client()
    try:
        result = (
            client.table("jobs")
            .select("*, profiles!client_id(full_name, avatar_url, county, area)")
            .eq("id", job_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")
        return result.data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Job fetch failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch job detail.")


@router.post("/", status_code=201)
async def create_job(body: CreateJobRequest, user: ClientUser, session: CurrentSession):
    """Client creates a new job post."""
    client = get_user_client(session.access_token)
    data = body.model_dump()
    data["client_id"] = user.user_id
    data["status"] = "open"

    try:
        result = client.table("jobs").insert(data).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create job")

        job = result.data[0]
        logger.info("Job created", job_id=job["id"], client=user.user_id)
        return job
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Job creation failed",
            client_id=user.user_id,
            error=str(exc),
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None) if hasattr(exc, "details") else None,
            hint=getattr(exc, "hint", None) if hasattr(exc, "hint") else None,
        )
        raise _job_write_http_error(exc, default_detail="Failed to create job. Please try again.")


@router.patch("/{job_id}")
async def update_job(job_id: str, body: UpdateJobRequest, user: CurrentUser, session: CurrentSession):
    """Client updates their own job."""
    client = get_user_client(session.access_token)

    # Ownership check
    try:
        existing = client.table("jobs").select("id, client_id").eq("id", job_id).maybe_single().execute()
        if not existing.data or existing.data["client_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Not your job")

        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = client.table("jobs").update(updates).eq("id", job_id).execute()
        return result.data[0] if result.data else {}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Job update failed",
            job_id=job_id,
            user_id=user.user_id,
            error=str(exc),
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None) if hasattr(exc, "details") else None,
            hint=getattr(exc, "hint", None) if hasattr(exc, "hint") else None,
        )
        raise _job_write_http_error(exc, default_detail="Failed to update job.")


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, user: CurrentUser, session: CurrentSession):
    """Client cancels/removes their job."""
    client = get_user_client(session.access_token)
    try:
        existing = (
            client.table("jobs")
            .select("id, client_id, status")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )

        if not existing.data or existing.data["client_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Not your job")

        if existing.data["status"] == "active":
            raise HTTPException(
                status_code=400,
                detail="Cannot delete an active booking. Raise a dispute instead.",
            )

        client.table("jobs").update({"status": "cancelled"}).eq("id", job_id).execute()
        logger.info("Job cancelled", job_id=job_id, client_id=user.user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Job deletion failed",
            job_id=job_id,
            user_id=user.user_id,
            error=str(exc),
            code=getattr(exc, "code", None),
            details=getattr(exc, "details", None) if hasattr(exc, "details") else None,
            hint=getattr(exc, "hint", None) if hasattr(exc, "hint") else None,
        )
        raise _job_write_http_error(exc, default_detail="Failed to cancel job.")


@router.get("/{job_id}/applications")
async def list_job_applications(job_id: str, user: CurrentUser, session: CurrentSession):
    """Client views applications for their job."""
    client = get_user_client(session.access_token)

    try:
        # Verify ownership
        job = client.table("jobs").select("id, client_id").eq("id", job_id).maybe_single().execute()
        if not job.data or job.data["client_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Not your job")

        result = (
            client.table("applications")
            .select(
                "*, "
                "profiles!fundi_id(full_name, avatar_url, county, area, is_verified), "
                "fundi_profiles!fundi_id(trade, rating_avg, jobs_completed, rate_min, rate_max, skills, experience_years, kyc_status)"
            )
            .eq("job_id", job_id)
            .order("created_at", desc=False)
            .execute()
        )
        return {"data": result.data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Application listing failed", job_id=job_id, user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch applications.")
