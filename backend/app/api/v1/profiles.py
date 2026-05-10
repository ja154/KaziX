"""
app/api/v1/profiles.py
──────────────────────
Profile management, public profile views, and fundi search.

GET    /v1/profiles/       → search / list fundis (public)
GET    /v1/profiles/me     → my own full profile (auth required)
PATCH  /v1/profiles/me     → update my own profile (auth required)
GET    /v1/profiles/{id}   → public profile card for one user
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentSession, CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client, get_anon_client, get_user_client
from app.services.profile_defaults import build_default_profile_row

logger = get_logger(__name__)
router = APIRouter()

TRADE_EMOJIS = {
    "plumber": "🚿",
    "electrician": "⚡",
    "mason": "🧱",
    "mama_fua": "👗",
    "carpenter": "🪚",
    "painter": "🎨",
    "roofer": "🏠",
    "gardener": "🌿",
    "driver_mover": "🛻",
    "security": "🔒",
    "other": "🔧",
}


class UpdateMyProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = None
    county: str | None = None
    area: str | None = None
    mpesa_number: str | None = Field(default=None, pattern=r"^\+254[0-9]{9}$")
    preferred_language: Literal["en", "sw"] | None = None
    avatar_url: str | None = None
    trade: str | None = None
    bio: str | None = None
    rate_min: int | None = Field(default=None, ge=0)
    rate_max: int | None = Field(default=None, ge=0)
    experience_years: int | None = Field(default=None, ge=0, le=60)
    skills: list[str] | None = None
    service_radius_km: int | None = Field(default=None, ge=0, le=1000)
    is_available: bool | None = None

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            skill = str(raw or "").strip()
            if not skill:
                continue
            key = skill.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(skill[:60])
        return cleaned[:20]


def _profile_update_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PostgrestAPIError):
        error_blob = " ".join(
            str(part or "")
            for part in (exc.code, exc.message, exc.details, exc.hint)
        ).lower()
        if exc.code in {"23505"} and ("uq_profiles_phone" in error_blob or "phone" in error_blob):
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That phone number is already linked to another account. "
                    "Sign in instead or use a different number."
                ),
            )
        if exc.code in {"23502", "23514", "22P02"} and ("mpesa_number" in error_blob or "phone" in error_blob):
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Enter a valid Kenyan phone number in +2547XXXXXXXX format.",
            )

    return HTTPException(status_code=500, detail="Failed to save profile changes.")


def _collect_profile_sections(
    admin,
    user_id: str,
    *,
    public: bool,
    enforce_active: bool = False,
) -> dict:
    private_columns = (
        "id, role, full_name, phone, email, county, area, mpesa_number, "
        "preferred_language, avatar_url, is_verified, created_at, updated_at"
    )
    if enforce_active:
        private_columns = (
            "id, role, full_name, phone, email, county, area, mpesa_number, "
            "preferred_language, avatar_url, is_verified, is_suspended, "
            "created_at, updated_at"
        )

    profile = (
        admin.table("profiles")
        .select(
            private_columns
            if not public
            else (
                "id, role, full_name, county, area, preferred_language, avatar_url, "
                "is_verified, created_at, updated_at"
            )
        )
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not profile.data:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile_data = dict(profile.data)
    if not public and enforce_active and profile_data.pop("is_suspended", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended. Contact support.",
        )

    payload = {"profile": profile_data, "fundi_profile": None}

    if profile_data["role"] == "fundi":
        fundi = (
            admin.table("fundi_profiles")
            .select(
                "trade, bio, rate_min, rate_max, experience_years, "
                "skills, service_radius_km, rating_avg, jobs_completed, "
                "is_available, kyc_status, created_at, updated_at"
            )
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        payload["fundi_profile"] = fundi.data

    return payload


def _fetch_auth_user(access_token: str):
    try:
        response = get_anon_client().auth.get_user(jwt=access_token)
        return getattr(response, "user", None) if response else None
    except Exception as exc:
        logger.warning("Could not load auth user for profile bootstrap", error=str(exc))
        return None


def _ensure_profile_exists(admin, session: CurrentSession) -> dict:
    try:
        return _collect_profile_sections(
            admin,
            session.user_id,
            public=False,
            enforce_active=True,
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise

        auth_user = _fetch_auth_user(session.access_token)
        default_profile = build_default_profile_row(
            session.user_id,
            phone=getattr(auth_user, "phone", None),
            email=getattr(auth_user, "email", None),
        )

        try:
            admin.table("profiles").insert(default_profile).execute()
            logger.info(
                "Auto-created default profile from /v1/profiles/me",
                user_id=session.user_id,
                has_phone=bool(default_profile["phone"]),
                has_email=bool(default_profile["email"]),
            )
        except Exception as profile_exc:
            try:
                return _collect_profile_sections(
                    admin,
                    session.user_id,
                    public=False,
                    enforce_active=True,
                )
            except HTTPException as refetch_exc:
                if refetch_exc.status_code != status.HTTP_404_NOT_FOUND:
                    raise refetch_exc

            logger.warning(
                "Failed to auto-create default profile from /v1/profiles/me",
                user_id=session.user_id,
                error=str(profile_exc),
                code=getattr(profile_exc, "code", None),
            )
            raise exc

        return _collect_profile_sections(
            admin,
            session.user_id,
            public=False,
            enforce_active=True,
        )


# ── Search / list fundis ─────────────────────────────────────


@router.get("/")
async def search_fundis(
    trade: str | None = Query(None, description="Trade slug, e.g. plumber"),
    location: str | None = Query(None, description="County/city, e.g. Nairobi"),
    min_rate: int | None = Query(None, ge=0),
    max_rate: int | None = Query(None, ge=0),
    min_rating: float | None = Query(None, ge=0, le=5),
    verified_only: bool = Query(False),
    available_only: bool = Query(False),
    sort_by: Literal["rating", "jobs", "rate_asc", "rate_desc"] = Query("rating"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Public fundi search. Two-query approach — no PostgREST embedding used.
    No authentication required.
    """
    client = get_anon_client()
    try:
        fq = client.table("fundi_profiles").select(
            "id, trade, skills, rate_min, rate_max, "
            "rating_avg, jobs_completed, is_available, kyc_status"
        )
        if trade:
            fq = fq.ilike("trade", f"%{trade.lower().replace(' ', '_')}%")
        if min_rating is not None:
            fq = fq.gte("rating_avg", min_rating)
        if verified_only:
            fq = fq.eq("kyc_status", "approved")
        if available_only:
            fq = fq.eq("is_available", True)

        fundi_result = fq.limit(500).execute()
        fundi_rows = fundi_result.data or []

        if not fundi_rows:
            return {"total": 0, "offset": offset, "limit": limit, "results": []}

        fundi_ids = [row["id"] for row in fundi_rows]

        pq = (
            client.table("profiles")
            .select("id, full_name, avatar_url, county, area, is_verified")
            .in_("id", fundi_ids)
        )
        if location:
            pq = pq.ilike("county", f"%{location}%")

        profile_result = pq.execute()
        profiles_by_id = {profile["id"]: profile for profile in (profile_result.data or [])}

        fundis = []
        for fundi_profile in fundi_rows:
            profile = profiles_by_id.get(fundi_profile["id"])
            if not profile:
                continue

            trade_key = (fundi_profile.get("trade") or "other").lower()
            rate_min_val = int(fundi_profile.get("rate_min") or 0)
            rating = round(float(fundi_profile.get("rating_avg") or 0), 1)
            is_verified = bool(profile.get("is_verified")) or fundi_profile.get("kyc_status") == "approved"

            if min_rate is not None and min_rate > 0 and rate_min_val < min_rate:
                continue
            if max_rate is not None and rate_min_val > 0 and rate_min_val > max_rate:
                continue

            skills = fundi_profile.get("skills") or []
            if isinstance(skills, str):
                skills = [item.strip() for item in skills.split(",") if item.strip()]

            fundis.append(
                {
                    "id": fundi_profile["id"],
                    "full_name": profile.get("full_name") or "Fundi",
                    "avatar_url": profile.get("avatar_url"),
                    "trade": trade_key,
                    "trade_label": trade_key.replace("_", " ").title(),
                    "trade_emoji": TRADE_EMOJIS.get(trade_key, "🔧"),
                    "county": profile.get("county") or "",
                    "area": profile.get("area") or "",
                    "is_verified": is_verified,
                    "is_available": bool(fundi_profile.get("is_available")),
                    "rate_min": rate_min_val,
                    "rate_label": f"KES {rate_min_val:,}/hr" if rate_min_val else "Negotiable",
                    "rating": rating,
                    "jobs_completed": int(fundi_profile.get("jobs_completed") or 0),
                    "skills": skills[:4],
                }
            )

        sort_key = {
            "rating": lambda item: item["rating"],
            "jobs": lambda item: item["jobs_completed"],
            "rate_asc": lambda item: item["rate_min"],
            "rate_desc": lambda item: item["rate_min"],
        }.get(sort_by, lambda item: item["rating"])
        fundis.sort(key=sort_key, reverse=(sort_by != "rate_asc"))

        total = len(fundis)
        page = fundis[offset: offset + limit]

        return {"total": total, "offset": offset, "limit": limit, "results": page}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("fundi_search_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Search failed: {str(exc)[:200]}")


# ── My profile ───────────────────────────────────────────────


@router.get("/me")
async def get_my_profile(session: CurrentSession):
    """
    Returns the full private profile of the logged-in user.
    Includes fundi-specific profile data if applicable.
    Auto-creates a default profile if one does not exist yet.
    """
    admin = get_admin_client()
    try:
        return _ensure_profile_exists(admin, session)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch your profile.")


@router.patch("/me")
async def update_my_profile(
    body: UpdateMyProfileRequest,
    user: CurrentUser,
    session: CurrentSession,
):
    """
    Updates the authenticated user's profile.
    """
    provided_fields = set(body.model_fields_set)
    if not provided_fields:
        raise HTTPException(status_code=400, detail="No profile fields were provided.")

    admin = get_admin_client()
    client = get_user_client(session.access_token)

    try:
        current = _ensure_profile_exists(admin, session)
        current_profile = current["profile"]
        current_fundi = current["fundi_profile"] or {}
        role = current_profile["role"]

        profile_fields = {
            "full_name",
            "email",
            "county",
            "area",
            "mpesa_number",
            "preferred_language",
            "avatar_url",
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

        if role != "fundi" and provided_fields & fundi_fields:
            raise HTTPException(
                status_code=422,
                detail="Only fundi accounts can update trade, rates, skills, or availability.",
            )

        profile_updates = {
            field: getattr(body, field)
            for field in profile_fields
            if field in provided_fields
        }
        if profile_updates:
            client.table("profiles").update(profile_updates).eq("id", user.user_id).execute()

        if role == "fundi":
            next_rate_min = body.rate_min if "rate_min" in provided_fields else current_fundi.get("rate_min")
            next_rate_max = body.rate_max if "rate_max" in provided_fields else current_fundi.get("rate_max")
            if next_rate_min is not None and next_rate_max is not None and next_rate_max < next_rate_min:
                raise HTTPException(
                    status_code=422,
                    detail="Maximum rate must be greater than or equal to minimum rate.",
                )

            fundi_updates = {
                field: getattr(body, field)
                for field in fundi_fields
                if field in provided_fields
            }
            if fundi_updates:
                client.table("fundi_profiles").upsert(
                    {"id": user.user_id, **fundi_updates},
                    on_conflict="id",
                ).execute()

        return _collect_profile_sections(
            admin,
            user.user_id,
            public=False,
            enforce_active=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _profile_update_http_error(exc)


# ── Public profile card ──────────────────────────────────────


@router.get("/{user_id}")
async def get_public_profile(user_id: str):
    """
    Publicly accessible profile view for one user.
    Restricts sensitive fields and focuses on safe profile data.
    """
    client = get_anon_client()
    try:
        return _collect_profile_sections(client, user_id, public=True)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch public profile.")
