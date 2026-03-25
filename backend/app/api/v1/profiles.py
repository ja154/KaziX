"""
app/api/v1/profiles.py
──────────────────────
Profile management and public profile views.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client

logger = get_logger(__name__)
router = APIRouter()


class UpdateMyProfileRequest(BaseModel):
    # Shared profile fields
    full_name: str | None = Field(None, min_length=2, max_length=120)
    email: str | None = None
    county: str | None = None
    area: str | None = None
    avatar_url: str | None = None
    mpesa_number: str | None = None
    preferred_language: Literal["en", "sw"] | None = None
    # Fundi-specific fields
    trade: str | None = None
    bio: str | None = None
    rate_min: int | None = Field(None, ge=0)
    rate_max: int | None = Field(None, ge=0)
    experience_years: int | None = Field(None, ge=0, le=60)
    skills: list[str] | None = None
    service_radius_km: int | None = Field(None, ge=0, le=200)
    is_available: bool | None = None


@router.get("/me")
async def get_my_profile(user: CurrentUser):
    """
    Returns the full private profile of the logged-in user.
    Includes fundi-specific profile data if applicable.
    """
    admin = get_admin_client()
    try:
        result = admin.table("profiles").select("*").eq("id", user.user_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        fundi = None
        if result.data["role"] == "fundi":
            fp = admin.table("fundi_profiles").select("*").eq("id", user.user_id).maybe_single().execute()
            fundi = fp.data
            
        return {"profile": result.data, "fundi_profile": fundi}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch private profile", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch your profile.")


@router.patch("/me")
async def update_my_profile(body: UpdateMyProfileRequest, user: CurrentUser):
    """
    Partially updates the authenticated user's profile.
    Supports both shared profile fields and fundi-specific fields.
    """
    admin = get_admin_client()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    profile_fields = {
        "full_name",
        "email",
        "county",
        "area",
        "avatar_url",
        "mpesa_number",
        "preferred_language",
    }
    fundi_fields = {
        "trade",
        "bio",
        "rate_min",
        "rate_max",
        "experience_years",
        "skills",
        "service_radius_km",
        "is_available",
    }

    profile_updates = {k: v for k, v in updates.items() if k in profile_fields}
    fundi_updates = {k: v for k, v in updates.items() if k in fundi_fields}

    try:
        me_result = (
            admin.table("profiles")
            .select("id, role")
            .eq("id", user.user_id)
            .single()
            .execute()
        )
        if not me_result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        role = me_result.data["role"]

        if profile_updates:
            admin.table("profiles").update(profile_updates).eq("id", user.user_id).execute()

        if fundi_updates:
            if role != "fundi":
                raise HTTPException(
                    status_code=403,
                    detail="Only fundis can update fundi profile fields",
                )

            existing_fundi = (
                admin.table("fundi_profiles")
                .select("id")
                .eq("id", user.user_id)
                .maybe_single()
                .execute()
            )
            if existing_fundi.data:
                admin.table("fundi_profiles").update(fundi_updates).eq("id", user.user_id).execute()
            else:
                # First creation still requires a trade value.
                if "trade" not in fundi_updates:
                    raise HTTPException(
                        status_code=422,
                        detail="Trade is required to create a fundi profile.",
                    )
                admin.table("fundi_profiles").insert(
                    {"id": user.user_id, **fundi_updates}
                ).execute()

        profile = admin.table("profiles").select("*").eq("id", user.user_id).single().execute()
        fundi_profile = None
        if profile.data and profile.data.get("role") == "fundi":
            fp = (
                admin.table("fundi_profiles")
                .select("*")
                .eq("id", user.user_id)
                .maybe_single()
                .execute()
            )
            fundi_profile = fp.data

        return {"profile": profile.data, "fundi_profile": fundi_profile}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update profile", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update your profile.")


@router.get("/{user_id}")
async def get_public_profile(user_id: str):
    """
    Publicly accessible profile view. 
    Restricts sensitive fields and focuses on fundi marketing data.
    """
    from app.core.supabase import get_anon_client
    client = get_anon_client()
    try:
        result = (
            client.table("profiles")
            .select("id, full_name, avatar_url, county, area, role, is_verified")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
            
        p = result.data
        if p["role"] == "fundi":
            fp = client.table("fundi_profiles").select(
                "trade, bio, rate_min, rate_max, experience_years, "
                "skills, service_radius_km, rating_avg, jobs_completed, is_available, kyc_status"
            ).eq("id", user_id).maybe_single().execute()
            p["fundi_profile"] = fp.data
            
        return p
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch public profile", target=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch public profile.")
