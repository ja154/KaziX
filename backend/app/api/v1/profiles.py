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
    trade:          str | None = Query(None, description="Trade slug, e.g. plumber"),
    location:       str | None = Query(None, description="County/city, e.g. Nairobi"),
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
    No authentication required.
    """
    client = get_anon_client()
    try:
        # Query profiles (role=fundi) with embedded fundi_profiles data.
        # Filtering on fundi-specific fields is done in Python after the join
        # to avoid PostgREST embedded-filter compatibility issues.
        query = (
            client.table("profiles")
            .select(
                "id, full_name, avatar_url, county, area, is_verified, "
                "fundi_profiles(trade, skills, rate_min, rate_max, "
                "rating_avg, jobs_completed, is_available, kyc_status)"
            )
            .eq("role", "fundi")
        )

        # Location filter — applied directly on profiles.county
        if location:
            query = query.ilike("county", f"%{location}%")

        # Fetch a generous page so we can filter in Python
        fetch_limit = min(limit * 5, 200)
        result = query.range(0, offset + fetch_limit - 1).execute()
        rows = result.data or []

        # ── Python-side filters ────────────────────────────────
        fundis = []
        for row in rows:
            fp = row.get("fundi_profiles")
            # fundi_profiles is a list (one-to-one embedded as array in PostgREST)
            if isinstance(fp, list):
                fp = fp[0] if fp else None

            if not fp:
                continue  # no fundi profile record — skip

            trade_key = (fp.get("trade") or "other").lower()

            # Trade filter
            if trade and trade.lower() not in trade_key and trade_key not in (trade or "").lower():
                continue

            rate_min_val = fp.get("rate_min") or 0
            # Rate filter
            if min_rate is not None and rate_min_val < min_rate:
                continue
            if max_rate is not None and rate_min_val > max_rate:
                continue

            # Rating filter
            rating = float(fp.get("rating_avg") or 0)
            if min_rating is not None and rating < min_rating:
                continue

            # Verified filter
            is_verified = bool(row.get("is_verified")) or fp.get("kyc_status") == "approved"
            if verified_only and not is_verified:
                continue

            # Availability filter
            is_available = bool(fp.get("is_available"))
            if available_only and not is_available:
                continue

            # Skills: stored as array or comma string
            skills = fp.get("skills") or []
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(",") if s.strip()]

            fundis.append({
                "id":            row["id"],
                "full_name":     row.get("full_name") or "Fundi",
                "avatar_url":    row.get("avatar_url"),
                "trade":         trade_key,
                "trade_label":   trade_key.replace("_", " ").title(),
                "trade_emoji":   TRADE_EMOJIS.get(trade_key, "🔧"),
                "county":        row.get("county") or "",
                "area":          row.get("area") or "",
                "is_verified":   is_verified,
                "is_available":  is_available,
                "rate_min":      rate_min_val,
                "rate_label":    f"KES {rate_min_val:,}/hr" if rate_min_val else "Negotiable",
                "rating":        round(rating, 1),
                "jobs_completed": int(fp.get("jobs_completed") or 0),
                "skills":        skills[:4],
            })

        # ── Sort ──────────────────────────────────────────────
        if sort_by == "rating":
            fundis.sort(key=lambda f: f["rating"], reverse=True)
        elif sort_by == "jobs":
            fundis.sort(key=lambda f: f["jobs_completed"], reverse=True)
        elif sort_by == "rate_asc":
            fundis.sort(key=lambda f: f["rate_min"])
        elif sort_by == "rate_desc":
            fundis.sort(key=lambda f: f["rate_min"], reverse=True)

        # ── Paginate ──────────────────────────────────────────
        total   = len(fundis)
        page    = fundis[offset: offset + limit]

        return {"total": total, "offset": offset, "limit": limit, "results": page}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("fundi_search_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Search failed: {str(exc)[:120]}")


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
