"""
app/api/v1/dashboard.py
───────────────────────
Role-aware dashboard state for authenticated client and fundi accounts.

GET /v1/dashboard/state → sidebar counts, summary cards, recent items, and
monthly series derived from live jobs, applications, bookings, and payments.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client

logger = get_logger(__name__)
router = APIRouter()

PLATFORM_FEE_RATE = 0.10
MONTH_SERIES_LENGTH = 6


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sort_rows_by_created_at(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: _parse_datetime(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _status_counts(rows: list[dict]) -> Counter:
    return Counter(str(row.get("status") or "").strip() for row in rows)


def _month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def _month_label(value: datetime) -> str:
    return value.strftime("%b")


def _recent_month_starts(now: datetime, count: int = MONTH_SERIES_LENGTH) -> list[datetime]:
    months: list[datetime] = []
    year = now.year
    month = now.month

    for _ in range(count):
        months.append(datetime(year, month, 1, tzinfo=timezone.utc))
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    months.reverse()
    return months


def _empty_month_series(now: datetime) -> list[dict]:
    return [
        {"key": _month_key(month_start), "label": _month_label(month_start), "amount": 0}
        for month_start in _recent_month_starts(now)
    ]


def _with_month_amounts(now: datetime, amounts_by_month: dict[str, int]) -> list[dict]:
    series = _empty_month_series(now)
    for item in series:
        item["amount"] = _safe_int(amounts_by_month.get(item["key"]))
    return series


def _client_transaction_delta(transaction: dict) -> int:
    if transaction.get("status") != "confirmed":
        return 0

    amount = _safe_int(transaction.get("amount"))
    if transaction.get("type") == "escrow_in":
        return amount
    if transaction.get("type") == "refund":
        return -amount
    return 0


def _worker_booking_fee(gross_amount: int) -> int:
    return int(round(gross_amount * PLATFORM_FEE_RATE))


def _worker_booking_net(gross_amount: int) -> int:
    fee = _worker_booking_fee(gross_amount)
    return max(gross_amount - fee, 0)


def _client_recent_jobs(jobs: list[dict], applications: list[dict]) -> list[dict]:
    applications_by_job: dict[str, list[dict]] = {}
    for application in applications:
        job_id = application.get("job_id")
        if not job_id:
            continue
        applications_by_job.setdefault(job_id, []).append(application)

    recent: list[dict] = []
    for job in _sort_rows_by_created_at(jobs)[:4]:
        apps = applications_by_job.get(job.get("id"), [])
        recent.append(
            {
                "id": job.get("id"),
                "title": job.get("title") or "Untitled job",
                "trade": job.get("trade"),
                "county": job.get("county"),
                "area": job.get("area"),
                "status": job.get("status"),
                "created_at": job.get("created_at"),
                "budget_min": job.get("budget_min"),
                "budget_max": job.get("budget_max"),
                "application_count": len([app for app in apps if app.get("status") != "withdrawn"]),
                "pending_application_count": len([app for app in apps if app.get("status") == "pending"]),
            }
        )
    return recent


def _recent_bookings(bookings: list[dict], jobs_by_id: dict[str, dict]) -> list[dict]:
    recent: list[dict] = []
    for booking in _sort_rows_by_created_at(bookings)[:4]:
        job = jobs_by_id.get(booking.get("job_id"), {})
        recent.append(
            {
                "id": booking.get("id"),
                "job_id": booking.get("job_id"),
                "title": job.get("title") or "Untitled job",
                "trade": job.get("trade"),
                "county": job.get("county"),
                "area": job.get("area"),
                "status": booking.get("status"),
                "escrow_status": booking.get("escrow_status"),
                "agreed_amount": _safe_int(booking.get("agreed_amount")),
                "start_date": booking.get("start_date"),
                "created_at": booking.get("created_at"),
                "updated_at": booking.get("updated_at"),
                "escrow_held_at": booking.get("escrow_held_at"),
                "escrow_released_at": booking.get("escrow_released_at"),
                "mpesa_receipt": booking.get("mpesa_receipt"),
            }
        )
    return recent


def _recent_transactions(transactions: list[dict], bookings_by_id: dict[str, dict], jobs_by_id: dict[str, dict]) -> list[dict]:
    recent: list[dict] = []
    for transaction in _sort_rows_by_created_at(transactions)[:10]:
        booking = bookings_by_id.get(transaction.get("booking_id"), {})
        job = jobs_by_id.get(booking.get("job_id"), {})
        recent.append(
            {
                "id": transaction.get("id"),
                "booking_id": transaction.get("booking_id"),
                "job_id": booking.get("job_id"),
                "title": job.get("title") or "Untitled job",
                "type": transaction.get("type"),
                "amount": _safe_int(transaction.get("amount")),
                "status": transaction.get("status"),
                "mpesa_ref": transaction.get("mpesa_ref"),
                "created_at": transaction.get("created_at"),
                "escrow_status": booking.get("escrow_status"),
            }
        )
    return recent


def _build_client_state(now: datetime, jobs: list[dict], applications: list[dict], bookings: list[dict], transactions: list[dict]) -> dict:
    job_counts = _status_counts(jobs)
    application_counts = _status_counts(applications)
    booking_counts = _status_counts(bookings)
    jobs_by_id = {job.get("id"): job for job in jobs if job.get("id")}
    bookings_by_id = {booking.get("id"): booking for booking in bookings if booking.get("id")}

    monthly_spend: dict[str, int] = {}
    total_spent = 0
    refunded_total = 0

    for transaction in transactions:
        delta = _client_transaction_delta(transaction)
        if transaction.get("status") == "confirmed" and transaction.get("type") == "refund":
            refunded_total += _safe_int(transaction.get("amount"))
        total_spent += delta

        created_at = _parse_datetime(transaction.get("created_at"))
        if created_at is None:
            continue
        key = _month_key(created_at)
        monthly_spend[key] = monthly_spend.get(key, 0) + delta

    paid_bookings = [booking for booking in bookings if booking.get("status") != "cancelled"]
    active_contracts = sum(
        1 for booking in bookings if booking.get("status") in {"confirmed", "in_progress"}
    )
    active_applications = len(
        [application for application in applications if application.get("status") != "withdrawn"]
    )
    in_escrow_amount = sum(
        _safe_int(booking.get("agreed_amount"))
        for booking in bookings
        if booking.get("escrow_status") == "held"
    )
    this_month_key = _month_key(now)

    return {
        "jobs": {
            "total": len(jobs),
            "open": job_counts.get("open", 0),
            "reviewing": job_counts.get("reviewing", 0),
            "active": job_counts.get("active", 0),
            "completed": job_counts.get("completed", 0),
            "closed": job_counts.get("cancelled", 0) + job_counts.get("expired", 0),
            "live": job_counts.get("open", 0) + job_counts.get("reviewing", 0) + job_counts.get("active", 0),
        },
        "applications": {
            "total": active_applications,
            "pending": application_counts.get("pending", 0),
            "shortlisted": application_counts.get("shortlisted", 0),
            "hired": application_counts.get("hired", 0),
            "rejected": application_counts.get("rejected", 0),
            "withdrawn": application_counts.get("withdrawn", 0),
        },
        "hires": {
            "active": active_contracts,
            "confirmed": booking_counts.get("confirmed", 0),
            "in_progress": booking_counts.get("in_progress", 0),
            "completed": booking_counts.get("completed", 0),
            "cancelled": booking_counts.get("cancelled", 0),
        },
        "payments": {
            "total_spent": max(total_spent, 0),
            "in_escrow": in_escrow_amount,
            "this_month": monthly_spend.get(this_month_key, 0),
            "refunded_total": refunded_total,
            "avg_job_value": round(
                sum(_safe_int(booking.get("agreed_amount")) for booking in paid_bookings) / len(paid_bookings)
            ) if paid_bookings else 0,
            "active_escrows": len([booking for booking in bookings if booking.get("escrow_status") == "held"]),
        },
        "recent_jobs": _client_recent_jobs(jobs, applications),
        "recent_hires": _recent_bookings(bookings, jobs_by_id),
        "recent_transactions": _recent_transactions(transactions, bookings_by_id, jobs_by_id),
        "monthly_spend": _with_month_amounts(now, monthly_spend),
    }


def _build_fundi_state(
    now: datetime,
    fundi_profile: dict,
    open_jobs: list[dict],
    applications: list[dict],
    bookings: list[dict],
    jobs_by_id: dict[str, dict],
) -> dict:
    application_counts = _status_counts(applications)
    booking_counts = _status_counts(bookings)

    monthly_gross: dict[str, int] = {}
    gross_released_total = 0

    for booking in bookings:
        if booking.get("escrow_status") != "released":
            continue

        gross_amount = _safe_int(booking.get("agreed_amount"))
        gross_released_total += gross_amount

        released_at = _parse_datetime(booking.get("escrow_released_at")) or _parse_datetime(booking.get("updated_at"))
        if released_at is None:
            continue
        key = _month_key(released_at)
        monthly_gross[key] = monthly_gross.get(key, 0) + gross_amount

    monthly_earnings = []
    for item in _empty_month_series(now):
        gross = _safe_int(monthly_gross.get(item["key"]))
        fee = _worker_booking_fee(gross)
        monthly_earnings.append(
            {
                "key": item["key"],
                "label": item["label"],
                "gross": gross,
                "fee": fee,
                "net": max(gross - fee, 0),
            }
        )

    active_contracts = sum(
        1 for booking in bookings if booking.get("status") in {"confirmed", "in_progress"}
    )
    active_applications = len(
        [application for application in applications if application.get("status") != "withdrawn"]
    )
    in_escrow_amount = sum(
        _safe_int(booking.get("agreed_amount"))
        for booking in bookings
        if booking.get("escrow_status") == "held"
    )
    this_month_key = _month_key(now)
    this_month_gross = _safe_int(monthly_gross.get(this_month_key))
    rating_avg = fundi_profile.get("rating_avg")
    try:
        rating_value = round(float(rating_avg or 0), 2)
    except (TypeError, ValueError):
        rating_value = 0

    recent_alerts = []
    for job in _sort_rows_by_created_at(open_jobs)[:4]:
        recent_alerts.append(
            {
                "id": job.get("id"),
                "title": job.get("title") or "Untitled job",
                "trade": job.get("trade"),
                "county": job.get("county"),
                "area": job.get("area"),
                "budget_min": job.get("budget_min"),
                "budget_max": job.get("budget_max"),
                "urgency": job.get("urgency"),
                "created_at": job.get("created_at"),
            }
        )

    return {
        "availability": {
            "is_available": bool(fundi_profile.get("is_available", True)),
            "trade": fundi_profile.get("trade"),
        },
        "alerts": {
            "total": len(open_jobs),
        },
        "applications": {
            "total": active_applications,
            "pending": application_counts.get("pending", 0),
            "shortlisted": application_counts.get("shortlisted", 0),
            "hired": application_counts.get("hired", 0),
            "rejected": application_counts.get("rejected", 0),
            "withdrawn": application_counts.get("withdrawn", 0),
        },
        "contracts": {
            "active": active_contracts,
            "confirmed": booking_counts.get("confirmed", 0),
            "in_progress": booking_counts.get("in_progress", 0),
            "completed": booking_counts.get("completed", 0),
            "cancelled": booking_counts.get("cancelled", 0),
            "in_escrow": in_escrow_amount,
        },
        "earnings": {
            "gross_released_total": gross_released_total,
            "platform_fees_total": _worker_booking_fee(gross_released_total),
            "net_released_total": _worker_booking_net(gross_released_total),
            "this_month_gross": this_month_gross,
            "this_month_net": _worker_booking_net(this_month_gross),
        },
        "rating": {
            "average": rating_value,
            "completed_jobs": _safe_int(fundi_profile.get("jobs_completed")),
        },
        "recent_alerts": recent_alerts,
        "recent_contracts": _recent_bookings(bookings, jobs_by_id),
        "monthly_earnings": monthly_earnings,
    }


@router.get("/state")
async def get_dashboard_state(user: CurrentUser):
    admin = get_admin_client()
    now = datetime.now(timezone.utc)

    try:
        if user.role == "client":
            jobs = (
                admin.table("jobs")
                .select(
                    "id, client_id, title, trade, county, area, budget_min, budget_max, "
                    "payment_type, urgency, preferred_date, preferred_time, status, created_at, updated_at"
                )
                .eq("client_id", user.user_id)
                .order("created_at", desc=True)
                .execute()
            ).data or []

            job_ids = [job.get("id") for job in jobs if job.get("id")]
            applications: list[dict] = []
            if job_ids:
                applications = (
                    admin.table("applications")
                    .select("id, job_id, status, bid_amount, created_at, updated_at")
                    .in_("job_id", job_ids)
                    .order("created_at", desc=True)
                    .execute()
                ).data or []

            bookings = (
                admin.table("bookings")
                .select(
                    "id, job_id, client_id, fundi_id, agreed_amount, start_date, status, "
                    "escrow_status, mpesa_receipt, created_at, updated_at, escrow_held_at, escrow_released_at"
                )
                .eq("client_id", user.user_id)
                .order("created_at", desc=True)
                .execute()
            ).data or []

            booking_ids = [booking.get("id") for booking in bookings if booking.get("id")]
            transactions: list[dict] = []
            if booking_ids:
                transactions = (
                    admin.table("transactions")
                    .select("id, booking_id, type, amount, mpesa_ref, status, created_at")
                    .in_("booking_id", booking_ids)
                    .order("created_at", desc=True)
                    .execute()
                ).data or []

            client_state = _build_client_state(now, jobs, applications, bookings, transactions)
            return {
                "role": "client",
                "generated_at": now.isoformat(),
                "nav": {
                    "jobs": client_state["jobs"]["total"],
                    "applications": client_state["applications"]["total"],
                    "hires": client_state["hires"]["active"],
                    "saved_workers": None,
                    "messages": None,
                },
                "client": client_state,
            }

        if user.role == "fundi":
            fundi_profile_result = (
                admin.table("fundi_profiles")
                .select("id, trade, rating_avg, jobs_completed, is_available")
                .eq("id", user.user_id)
                .maybe_single()
                .execute()
            )
            fundi_profile = fundi_profile_result.data or {}

            applications = (
                admin.table("applications")
                .select("id, job_id, status, bid_amount, created_at, updated_at")
                .eq("fundi_id", user.user_id)
                .order("created_at", desc=True)
                .execute()
            ).data or []

            bookings = (
                admin.table("bookings")
                .select(
                    "id, job_id, client_id, fundi_id, agreed_amount, start_date, status, "
                    "escrow_status, mpesa_receipt, created_at, updated_at, escrow_held_at, escrow_released_at"
                )
                .eq("fundi_id", user.user_id)
                .order("created_at", desc=True)
                .execute()
            ).data or []

            tracked_job_ids = {
                row.get("job_id")
                for row in applications + bookings
                if row.get("job_id")
            }
            tracked_jobs: list[dict] = []
            if tracked_job_ids:
                tracked_jobs = (
                    admin.table("jobs")
                    .select("id, client_id, title, trade, county, area, budget_min, budget_max, urgency, created_at")
                    .in_("id", list(tracked_job_ids))
                    .execute()
                ).data or []
            jobs_by_id = {job.get("id"): job for job in tracked_jobs if job.get("id")}

            open_jobs_query = (
                admin.table("jobs")
                .select("id, client_id, title, trade, county, area, budget_min, budget_max, urgency, created_at, status")
                .eq("status", "open")
                .order("created_at", desc=True)
            )
            if fundi_profile.get("trade"):
                open_jobs_query = open_jobs_query.eq("trade", fundi_profile["trade"])
            open_jobs = open_jobs_query.execute().data or []
            open_jobs = [job for job in open_jobs if job.get("client_id") != user.user_id]

            fundi_state = _build_fundi_state(now, fundi_profile, open_jobs, applications, bookings, jobs_by_id)
            return {
                "role": "fundi",
                "generated_at": now.isoformat(),
                "nav": {
                    "find_jobs": fundi_state["alerts"]["total"],
                    "applications": fundi_state["applications"]["total"],
                    "contracts": fundi_state["contracts"]["active"],
                    "messages": None,
                },
                "fundi": fundi_state,
            }

        return {
            "role": user.role,
            "generated_at": now.isoformat(),
            "nav": {},
        }
    except Exception as exc:
        logger.error("Failed to build dashboard state", user_id=user.user_id, role=user.role, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard state.")
