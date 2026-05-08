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
    Public fundi search. Two-query approach — no PostgREST embedding used.
    No authentication required.
    """
    client = get_anon_client()
    try:
        # ── Step 1: query fundi_profiles with fundi-specific filters ──
        fq = client.table("fundi_profiles").select(
            "id, trade, skills, rate_min, rate_max, "
            "rating_avg, jobs_completed, is_available, kyc_status"
        )
        if trade:
            fq = fq.ilike("trade", f"%{trade.lower().replace(' ', '_')}%")
        # NOTE: rate_min can be NULL in the DB (means "Negotiable").
        # PostgreSQL NULL comparisons always return NULL/false, so we must
        # NOT apply rate filters at the DB level — do them in Python instead.
        if min_rating is not None:
            fq = fq.gte("rating_avg", min_rating)
        if verified_only:
            fq = fq.eq("kyc_status", "approved")
        if available_only:
            fq = fq.eq("is_available", True)

        fundi_result = fq.limit(500).execute()
        fundi_rows   = fundi_result.data or []

        if not fundi_rows:
            return {"total": 0, "offset": offset, "limit": limit, "results": []}

        # ── Step 2: fetch profile data for those IDs ──────────────────
        fundi_ids = [r["id"] for r in fundi_rows]

        pq = (
            client.table("profiles")
            .select("id, full_name, avatar_url, county, area, is_verified")
            .in_("id", fundi_ids)
        )
        if location:
            pq = pq.ilike("county", f"%{location}%")

        profile_result  = pq.execute()
        profiles_by_id  = {p["id"]: p for p in (profile_result.data or [])}

        # ── Step 3: combine, filter, sort, paginate ───────────────────
        fundis = []
        for fp in fundi_rows:
            profile = profiles_by_id.get(fp["id"])
            if not profile:
                continue  # excluded by location filter or RLS

            trade_key    = (fp.get("trade") or "other").lower()
            # NULL rate_min means "Negotiable" — treat as 0 for comparisons.
            # This avoids PostgreSQL NULL-comparison false negatives.
            rate_min_val = int(fp.get("rate_min") or 0)
            rating       = round(float(fp.get("rating_avg") or 0), 1)
            is_verified  = (
                bool(profile.get("is_verified")) or
                fp.get("kyc_status") == "approved"
            )

            # NULL-safe rate filters (applied in Python, not at DB level)
            if min_rate is not None and min_rate > 0 and rate_min_val < min_rate:
                continue
            if max_rate is not None and rate_min_val > 0 and rate_min_val > max_rate:
                continue

            skills = fp.get("skills") or []
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(",") if s.strip()]

            fundis.append({
                "id":             fp["id"],
                "full_name":      profile.get("full_name") or "Fundi",
                "avatar_url":     profile.get("avatar_url"),
                "trade":          trade_key,
                "trade_label":    trade_key.replace("_", " ").title(),
                "trade_emoji":    TRADE_EMOJIS.get(trade_key, "🔧"),
                "county":         profile.get("county") or "",
                "area":           profile.get("area") or "",
                "is_verified":    is_verified,
                "is_available":   bool(fp.get("is_available")),
                "rate_min":       rate_min_val,
                "rate_label":     f"KES {rate_min_val:,}/hr" if rate_min_val else "Negotiable",
                "rating":         rating,
                "jobs_completed": int(fp.get("jobs_completed") or 0),
                "skills":         skills[:4],
            })

        # Sort
        sort_key = {
            "rating":   lambda f: f["rating"],
            "jobs":     lambda f: f["jobs_completed"],
            "rate_asc": lambda f: f["rate_min"],
            "rate_desc":lambda f: f["rate_min"],
        }.get(sort_by, lambda f: f["rating"])
        fundis.sort(key=sort_key, reverse=(sort_by != "rate_asc"))

        total = len(fundis)
        page  = fundis[offset: offset + limit]

        return {"total": total, "offset": offset, "limit": limit, "results": page}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("fundi_search_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Search failed: {str(exc)[:200]}")


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
            .select(
                "id, full_name, avatar_url, county, area, role, is_verified, "
                "preferred_language, created_at"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        p = result.data
        fundi_profile = None
        if p["role"] == "fundi":
            fp = client.table("fundi_profiles").select(
                "trade, bio, rate_min, rate_max, experience_years, "
                "skills, service_radius_km, rating_avg, jobs_completed, is_available, kyc_status"
            ).eq("id", user_id).maybe_single().execute()
            fundi_profile = fp.data

        return {"profile": p, "fundi_profile": fundi_profile}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to fetch public profile.")
