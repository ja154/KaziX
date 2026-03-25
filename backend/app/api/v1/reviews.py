"""
app/api/v1/reviews.py
─────────────────────
Review submission and public review listing.

POST /v1/reviews            → submit one review for a completed booking
GET  /v1/reviews/{user_id}  → public list/summary for a user's received reviews
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client, get_anon_client
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()


class CreateReviewRequest(BaseModel):
    booking_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=5, max_length=3000)
    quality: int | None = Field(None, ge=1, le=5)
    punctuality: int | None = Field(None, ge=1, le=5)
    communication: int | None = Field(None, ge=1, le=5)
    value_for_money: int | None = Field(None, ge=1, le=5)
    would_hire_again: bool | None = None


def _build_summary(rows: list[dict]) -> dict:
    rows = rows or []
    ratings = [int(r["rating"]) for r in rows if r.get("rating") is not None]
    count = len(ratings)
    average = round(sum(ratings) / count, 2) if count else 0.0

    breakdown = {str(star): 0 for star in range(1, 6)}
    for rating in ratings:
        breakdown[str(rating)] += 1

    return {
        "count": count,
        "average": average,
        "breakdown": breakdown,
    }


def _refresh_fundi_rating(admin_client, fundi_id: str) -> None:
    """Recomputes a fundi's aggregate rating fields after a new review."""
    reviews = (
        admin_client.table("reviews")
        .select("rating")
        .eq("reviewee_id", fundi_id)
        .execute()
    )
    ratings = [int(r["rating"]) for r in (reviews.data or []) if r.get("rating") is not None]
    rating_avg = round(sum(ratings) / len(ratings), 2) if ratings else 0

    completed_jobs = (
        admin_client.table("bookings")
        .select("id")
        .eq("fundi_id", fundi_id)
        .eq("status", "completed")
        .execute()
    )
    jobs_completed = len(completed_jobs.data or [])

    admin_client.table("fundi_profiles").update(
        {"rating_avg": rating_avg, "jobs_completed": jobs_completed}
    ).eq("id", fundi_id).execute()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def submit_review(body: CreateReviewRequest, user: CurrentUser):
    """
    Creates one review row per reviewer per booking.
    Reviewer must be a participant in the completed booking.
    """
    admin = get_admin_client()
    try:
        booking = (
            admin.table("bookings")
            .select("id, status, client_id, fundi_id")
            .eq("id", body.booking_id)
            .maybe_single()
            .execute()
        )
        if not booking.data:
            raise HTTPException(status_code=404, detail="Booking not found")

        b = booking.data
        participants = {b["client_id"], b["fundi_id"]}
        if user.user_id not in participants:
            raise HTTPException(status_code=403, detail="Not your booking")
        if b["status"] != "completed":
            raise HTTPException(status_code=400, detail="Reviews are allowed only for completed bookings")

        existing = (
            admin.table("reviews")
            .select("id")
            .eq("booking_id", body.booking_id)
            .eq("reviewer_id", user.user_id)
            .maybe_single()
            .execute()
        )
        if existing.data:
            raise HTTPException(status_code=409, detail="You already reviewed this booking")

        reviewee_id = b["fundi_id"] if user.user_id == b["client_id"] else b["client_id"]
        payload = {
            "booking_id": body.booking_id,
            "reviewer_id": user.user_id,
            "reviewee_id": reviewee_id,
            "rating": body.rating,
            "comment": body.comment.strip(),
            "quality": body.quality,
            "punctuality": body.punctuality,
            "communication": body.communication,
            "value_for_money": body.value_for_money,
            "would_hire_again": body.would_hire_again,
        }

        result = admin.table("reviews").insert(payload).execute()
        review = result.data[0] if result.data else payload

        # Update fundi aggregate stats when the review targets a fundi account.
        if reviewee_id == b["fundi_id"]:
            _refresh_fundi_rating(admin, reviewee_id)

        await create_notification(
            user_id=reviewee_id,
            type_="review",
            title="You received a new review",
            body=f"You got a {body.rating}-star review on KaziX.",
            action_url="/worker-reviews.html" if reviewee_id == b["fundi_id"] else "/reviews.html",
        )

        return review
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Review submission failed",
            booking_id=body.booking_id,
            reviewer_id=user.user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to submit review.")


@router.get("/{user_id}")
async def list_user_reviews(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Public endpoint listing reviews a user has received.
    """
    anon = get_anon_client()
    try:
        result = (
            anon.table("reviews")
            .select(
                "id, booking_id, reviewer_id, rating, comment, quality, punctuality, "
                "communication, value_for_money, would_hire_again, created_at, "
                "profiles!reviewer_id(full_name, avatar_url)"
            )
            .eq("reviewee_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        rows = result.data or []
        summary = _build_summary(rows)
        return {"data": rows, "summary": summary}
    except Exception as exc:
        logger.error("Review listing failed", reviewee_id=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch reviews.")
