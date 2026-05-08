"""
app/api/v1/profiles.py
──────────────────────
Profile management, public profile views, and fundi search.

GET  /v1/profiles/              → search / list fundis (public)
GET  /v1/profiles/me            → my own full profile (auth required)
GET  /v1/profiles/{user_id}     → public profile card for one fundi
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from app.api.deps import CurrentUser
from app.core.supabase import get_admin_client, get_anon_client
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

TRADE_EMOJIS = {
    "plumber": "🚿", "electrician": "⚡", "mason": "🧱",
    "mama_fua": "👗", "carpenter": "🪚", "painter": "🎨",
    "roofer": "🏠", "gardener": "🌿", "driver_mover": "🛻",
    "security": "🔒", "other": "🔧",
}


# ── Search / list fundis ─────────────────────────────────────

@router.get("/")
async def search_fundis(
    trade:          str | None = Query(None, description="Filter by trade slug, e.g. plumber"),
    location:       str | None = Query(None, description="Filter by county/area, e.g. Nairobi"),
    min_rate:       int | None = Query(None, ge=0),
    max_rate:       int | None = Query(None, ge=0),
    min_rating:     float | None = Query(None, ge=0, le=5),
    verified_only:  bool = Query(False),
    available_only: bool = Query(False),
    sort_by: Literal["rating", "jobs", "rate_asc", "rate_desc"] = Query("rating"),
    limit:   int = Query(20, ge=1, le=100),
    offset:  int = Query(0, ge=0),
):
    """
    Public search endpoint for finding fundis.
    Returns a paginated list of fundi profiles with their trade data.
    No authentication required.
    """
    client = get_anon_client()
    try:
        query = client.table("fundi_profiles").select(
            "id, trade, skills, rate_min, rate_max, "
            "rating_avg, jobs_completed, is_available, kyc_status, "
            "profiles!inner(full_name, avatar_url, county, area, is_verified)"
        )

        # ── Fundi-table filters ──────────────────────────────
        if trade:
            query = query.ilike("trade", f"%{trade.lower().replace(' ', '_')}%")
        if min_rate is not None:
            query = query.lte("rate_min", max_rate if max_rate else 999_999)
        if max_rate is not None:
            query = query.gte("rate_min", 0).lte("rate_min", max_rate)
        if min_rating is not None:
            query = query.gte("rating_avg", min_rating)
        if verified_only:
            query = query.eq("kyc_status", "approved")
        if available_only:
            query = query.eq("is_available", True)

        # ── Location filter on joined profiles table ─────────
        if location:
            query = query.filter("profiles.county", "ilike", f"%{location}%")

        # ── Sort ─────────────────────────────────────────────
        if sort_by == "rating":
            query = query.order("rating_avg", desc=True)
        elif sort_by == "jobs":
            query = query.order("jobs_completed", desc=True)
        elif sort_by == "rate_asc":
            query = query.order("rate_min", desc=False)
        elif sort_by == "rate_desc":
            query = query.order("rate_min", desc=True)

        # ── Pagination ────────────────────────────────────────
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        rows = result.data or []

        # ── Shape response ────────────────────────────────────
        fundis = []
        for row in rows:
            profile = row.get("profiles") or {}
            trade_key = (row.get("trade") or "other").lower()
            skills = row.get("skills") or []
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(",") if s.strip()]

            rate_min = row.get("rate_min") or 0
            rate_label = f"KES {rate_min:,}/hr" if rate_min else "Negotiable"
            rating = row.get("rating_avg") or 0.0
            jobs = row.get("jobs_completed") or 0

            fundis.append({
                "id": row["id"],
                "full_name": profile.get("full_name") or "Fundi",
                "avatar_url": profile.get("avatar_url"),
                "trade": trade_key,
                "trade_label": trade_key.replace("_", " ").title(),
                "trade_emoji": TRADE_EMOJIS.get(trade_key, "🔧"),
                "county": profile.get("county") or "",
                "area": profile.get("area") or "",
                "is_verified": bool(profile.get("is_verified")) or row.get("kyc_status") == "approved",
                "is_available": bool(row.get("is_available")),
                "rate_min": rate_min,
                "rate_label": rate_label,
                "rating": round(float(rating), 1),
                "jobs_completed": jobs,
                "skills": skills[:4],
            })

        return {
            "total": len(fundis),
            "offset": offset,
            "limit": limit,
            "results": fundis,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("fundi_search_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Search failed. Please try again.")


# ── My profile ───────────────────────────────────────────────

@router.get("/me")
async def get_my_profile(user: CurrentUser):
    """Returns the full private profile of the logged-in user."""
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
        raise HTTPException(status_code=500, detail="Failed to fetch your profile.")


# ── Public profile card ──────────────────────────────────────

@router.get("/{user_id}")
async def get_public_profile(user_id: str):
    """Publicly accessible profile view for one fundi."""
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
        raise HTTPException(status_code=500, detail="Failed to fetch public profile.")
