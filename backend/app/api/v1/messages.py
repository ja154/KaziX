from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client
from app.services.notifications import create_notification

logger = get_logger(__name__)
router = APIRouter()


class SendMessageRequest(BaseModel):
    participant_id: str
    body: str = Field(..., min_length=1, max_length=2000)
    job_id: str | None = None
    application_id: str | None = None
    booking_id: str | None = None


def _messages_http_error(exc: Exception, *, default_detail: str) -> HTTPException:
    if isinstance(exc, PostgrestAPIError):
        error_blob = " ".join(
            str(part or "")
            for part in (exc.code, exc.message, exc.details, exc.hint)
        ).lower()

        if exc.code == "PGRST205" and "public.messages" in error_blob:
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Messaging is not ready yet. The database migration for messages still needs to be applied.",
            )

        if (
            exc.code in {"42501", "PGRST301", "PGRST302"}
            or "row-level security" in error_blob
            or "permission denied" in error_blob
        ):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this conversation.",
            )

    return HTTPException(status_code=500, detail=default_detail)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_row(admin, table_name: str, select: str, field: str, value: str):
    result = (
        admin.table(table_name)
        .select(select)
        .eq(field, value)
        .maybe_single()
        .execute()
    )
    return result.data if result is not None else None


def _fetch_rows(
    admin,
    table_name: str,
    select: str,
    filters: dict[str, str | None],
    *,
    desc: bool = False,
):
    query = admin.table(table_name).select(select)
    for field, value in filters.items():
        if value is None:
            continue
        query = query.eq(field, value)
    result = query.order("created_at", desc=desc).execute()
    if result is None:
        return []
    return result.data or []


def _merge_messages(*collections: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for collection in collections:
        for row in collection:
            row_id = row.get("id")
            if row_id:
                by_id[row_id] = row
    return sorted(by_id.values(), key=lambda row: row.get("created_at") or "")


def _message_thread_id(message: dict) -> str:
    return (
        str(message.get("application_id") or "")
        or str(message.get("booking_id") or "")
        or str(message.get("job_id") or "")
        or str(message.get("id") or "")
    )


def _message_preview(value: str | None) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= 120:
        return text
    return f"{text[:117]}..."


def _message_query_filters(context: dict) -> dict[str, str | None]:
    application = context.get("application") or {}
    booking = context.get("booking") or {}
    job = context.get("job") or {}
    if application.get("id"):
        return {"application_id": application["id"]}
    if booking.get("id"):
        return {"booking_id": booking["id"]}
    return {"job_id": job.get("id")}


def _message_action_url(context: dict, participant_id: str) -> str:
    parts = [f"participant={participant_id}"]
    job = context.get("job") or {}
    application = context.get("application") or {}
    booking = context.get("booking") or {}
    if job.get("id"):
        parts.append(f"job={job['id']}")
    if application.get("id"):
        parts.append(f"application={application['id']}")
    if booking.get("id"):
        parts.append(f"booking={booking['id']}")
    return f"/messages.html?{'&'.join(parts)}"


def _get_profile(admin, profile_id: str, cache: dict[str, dict | None]) -> dict | None:
    if profile_id not in cache:
        cache[profile_id] = _fetch_row(
            admin,
            "profiles",
            "id, role, full_name, avatar_url, county, area, phone",
            "id",
            profile_id,
        )
    return cache[profile_id]


def _get_fundi_profile(admin, profile_id: str, cache: dict[str, dict | None]) -> dict | None:
    if profile_id not in cache:
        cache[profile_id] = _fetch_row(
            admin,
            "fundi_profiles",
            "id, trade, rating_avg, jobs_completed",
            "id",
            profile_id,
        )
    return cache[profile_id]


def _get_job(admin, job_id: str, cache: dict[str, dict | None]) -> dict | None:
    if job_id not in cache:
        cache[job_id] = _fetch_row(
            admin,
            "jobs",
            "id, client_id, title, trade, county, area, status, created_at",
            "id",
            job_id,
        )
    return cache[job_id]


def _get_application(admin, application_id: str, cache: dict[str, dict | None]) -> dict | None:
    if application_id not in cache:
        cache[application_id] = _fetch_row(
            admin,
            "applications",
            "id, job_id, fundi_id, status, bid_amount, created_at",
            "id",
            application_id,
        )
    return cache[application_id]


def _get_booking(admin, booking_id: str, cache: dict[str, dict | None]) -> dict | None:
    if booking_id not in cache:
        cache[booking_id] = _fetch_row(
            admin,
            "bookings",
            "id, job_id, application_id, client_id, fundi_id, status, agreed_amount, start_date, created_at",
            "id",
            booking_id,
        )
    return cache[booking_id]


def _find_application_for_job_and_fundi(admin, job_id: str, fundi_id: str) -> dict | None:
    result = (
        admin.table("applications")
        .select("id, job_id, fundi_id, status, bid_amount, created_at")
        .eq("job_id", job_id)
        .eq("fundi_id", fundi_id)
        .maybe_single()
        .execute()
    )
    return result.data if result is not None else None


def _find_booking_for_job_and_fundi(admin, job_id: str, fundi_id: str) -> dict | None:
    result = (
        admin.table("bookings")
        .select("id, job_id, application_id, client_id, fundi_id, status, agreed_amount, start_date, created_at")
        .eq("job_id", job_id)
        .eq("fundi_id", fundi_id)
        .maybe_single()
        .execute()
    )
    return result.data if result is not None else None


def _resolve_thread_context(
    admin,
    *,
    user,
    participant_id: str,
    job_id: str | None,
    application_id: str | None,
    booking_id: str | None,
    profile_cache: dict[str, dict | None],
    fundi_profile_cache: dict[str, dict | None],
    job_cache: dict[str, dict | None],
    application_cache: dict[str, dict | None],
    booking_cache: dict[str, dict | None],
) -> dict:
    if not participant_id:
        raise HTTPException(status_code=422, detail="participant_id is required")
    if participant_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot create a conversation with yourself")

    participant = _get_profile(admin, participant_id, profile_cache)
    if not participant:
        raise HTTPException(status_code=404, detail="Conversation participant not found")

    booking = _get_booking(admin, booking_id, booking_cache) if booking_id else None
    if booking_id and not booking:
        if not any((application_id, job_id)):
            raise HTTPException(status_code=404, detail="Booking not found")
        booking_id = None

    if booking:
        if booking.get("application_id"):
            application_id = booking["application_id"]
        if booking.get("job_id"):
            job_id = booking["job_id"]

    application = _get_application(admin, application_id, application_cache) if application_id else None
    if application_id and not application:
        # Stale message links can still be recovered safely from the job + participant pair.
        if job_id:
            application_id = None
        else:
            raise HTTPException(status_code=404, detail="Application not found")

    if application and application.get("job_id"):
        job_id = application.get("job_id")

    job = _get_job(admin, job_id, job_cache) if job_id else None
    if job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not any((job, application, booking)):
        raise HTTPException(
            status_code=422,
            detail="A job, application, or booking context is required to open this conversation.",
        )

    if user.role != "admin":
        if booking:
            allowed = {booking.get("client_id"), booking.get("fundi_id")}
            if {user.user_id, participant_id} != allowed:
                raise HTTPException(status_code=403, detail="You can only message the other booking participant.")
        elif application and job:
            allowed = {job.get("client_id"), application.get("fundi_id")}
            if {user.user_id, participant_id} != allowed:
                raise HTTPException(status_code=403, detail="You can only message the participant on this application.")
        elif job:
            if user.user_id == job.get("client_id"):
                application = application or _find_application_for_job_and_fundi(admin, job["id"], participant_id)
                booking = booking or _find_booking_for_job_and_fundi(admin, job["id"], participant_id)
                if not application and not booking:
                    raise HTTPException(status_code=403, detail="This worker is not attached to that job.")
                if booking and booking.get("application_id") and not application:
                    application = _get_application(admin, booking["application_id"], application_cache)
            elif participant_id == job.get("client_id"):
                application = application or _find_application_for_job_and_fundi(admin, job["id"], user.user_id)
                booking = booking or _find_booking_for_job_and_fundi(admin, job["id"], user.user_id)
                if not application and not booking:
                    raise HTTPException(status_code=403, detail="You do not have access to message about that job.")
                if booking and booking.get("application_id") and not application:
                    application = _get_application(admin, booking["application_id"], application_cache)
            else:
                raise HTTPException(status_code=403, detail="You do not have access to this job conversation.")

    return {
        "participant": participant,
        "participant_fundi_profile": _get_fundi_profile(admin, participant_id, fundi_profile_cache),
        "job": job,
        "application": application,
        "booking": booking,
    }


def _build_thread_summary(
    admin,
    *,
    user_id: str,
    participant_id: str,
    context: dict,
    last_message: dict | None,
    unread_count: int,
    message_count: int,
    profile_cache: dict[str, dict | None],
    fundi_profile_cache: dict[str, dict | None],
) -> dict:
    participant = context.get("participant") or _get_profile(admin, participant_id, profile_cache) or {}
    participant_fundi_profile = context.get("participant_fundi_profile") or _get_fundi_profile(
        admin,
        participant_id,
        fundi_profile_cache,
    ) or {}
    job = context.get("job") or {}
    application = context.get("application") or {}
    booking = context.get("booking") or {}
    latest_timestamp = (
        (last_message or {}).get("created_at")
        or application.get("created_at")
        or booking.get("created_at")
        or job.get("created_at")
    )

    return {
        "thread_id": f"{_message_thread_id(last_message or context.get('application') or context.get('booking') or context.get('job') or {'id': participant_id})}:{participant_id}",
        "participant_id": participant_id,
        "participant_name": participant.get("full_name") or "KaziX user",
        "participant_avatar_url": participant.get("avatar_url"),
        "participant_role": participant.get("role") or "client",
        "participant_county": participant.get("county"),
        "participant_area": participant.get("area"),
        "participant_phone": participant.get("phone"),
        "participant_trade": participant_fundi_profile.get("trade"),
        "participant_rating": participant_fundi_profile.get("rating_avg"),
        "job_id": job.get("id"),
        "job_title": job.get("title"),
        "job_trade": job.get("trade"),
        "job_county": job.get("county"),
        "job_area": job.get("area"),
        "job_status": job.get("status"),
        "application_id": application.get("id"),
        "application_status": application.get("status"),
        "booking_id": booking.get("id"),
        "booking_status": booking.get("status"),
        "booking_start_date": booking.get("start_date"),
        "latest_message_preview": _message_preview((last_message or {}).get("body")) if last_message else "",
        "last_message_at": latest_timestamp,
        "last_message_sender_id": (last_message or {}).get("sender_id"),
        "unread_count": unread_count,
        "message_count": message_count,
        "has_messages": bool(last_message),
        "current_user_id": user_id,
    }


@router.get("/threads")
async def list_message_threads(user: CurrentUser):
    admin = get_admin_client()
    profile_cache: dict[str, dict | None] = {}
    fundi_profile_cache: dict[str, dict | None] = {}
    job_cache: dict[str, dict | None] = {}
    application_cache: dict[str, dict | None] = {}
    booking_cache: dict[str, dict | None] = {}

    try:
        sent = _fetch_rows(admin, "messages", "*", {"sender_id": user.user_id}, desc=True)
        received = _fetch_rows(admin, "messages", "*", {"recipient_id": user.user_id}, desc=True)
        rows = sorted(
            {row["id"]: row for row in sent + received}.values(),
            key=lambda row: row.get("created_at") or "",
            reverse=True,
        )

        grouped: dict[str, dict] = {}
        for row in rows:
            participant_id = row["recipient_id"] if row.get("sender_id") == user.user_id else row["sender_id"]
            thread_base = row.get("application_id") or row.get("booking_id") or row.get("job_id") or row["id"]
            key = f"{thread_base}:{participant_id}"
            if key not in grouped:
                grouped[key] = {
                    "participant_id": participant_id,
                    "last_message": row,
                    "unread_count": 0,
                    "message_count": 0,
                    "job_id": row.get("job_id"),
                    "application_id": row.get("application_id"),
                    "booking_id": row.get("booking_id"),
                }
            grouped[key]["message_count"] += 1
            if row.get("recipient_id") == user.user_id and not row.get("read_at"):
                grouped[key]["unread_count"] += 1

        threads = []
        for seed in grouped.values():
            try:
                context = _resolve_thread_context(
                    admin,
                    user=user,
                    participant_id=seed["participant_id"],
                    job_id=seed.get("job_id"),
                    application_id=seed.get("application_id"),
                    booking_id=seed.get("booking_id"),
                    profile_cache=profile_cache,
                    fundi_profile_cache=fundi_profile_cache,
                    job_cache=job_cache,
                    application_cache=application_cache,
                    booking_cache=booking_cache,
                )
                threads.append(
                    _build_thread_summary(
                        admin,
                        user_id=user.user_id,
                        participant_id=seed["participant_id"],
                        context=context,
                        last_message=seed["last_message"],
                        unread_count=seed["unread_count"],
                        message_count=seed["message_count"],
                        profile_cache=profile_cache,
                        fundi_profile_cache=fundi_profile_cache,
                    )
                )
            except HTTPException:
                logger.warning(
                    "Skipping inaccessible message thread",
                    user_id=user.user_id,
                    participant_id=seed["participant_id"],
                    job_id=seed.get("job_id"),
                    application_id=seed.get("application_id"),
                    booking_id=seed.get("booking_id"),
                )

        threads.sort(key=lambda row: row.get("last_message_at") or "", reverse=True)
        return {"data": threads}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load message threads", user_id=user.user_id, error=str(exc))
        raise _messages_http_error(exc, default_detail="Failed to fetch messages.")


@router.get("/thread")
async def get_message_thread(
    user: CurrentUser,
    participant_id: str,
    job_id: str | None = None,
    application_id: str | None = None,
    booking_id: str | None = None,
):
    admin = get_admin_client()
    profile_cache: dict[str, dict | None] = {}
    fundi_profile_cache: dict[str, dict | None] = {}
    job_cache: dict[str, dict | None] = {}
    application_cache: dict[str, dict | None] = {}
    booking_cache: dict[str, dict | None] = {}

    try:
        context = _resolve_thread_context(
            admin,
            user=user,
            participant_id=participant_id,
            job_id=job_id,
            application_id=application_id,
            booking_id=booking_id,
            profile_cache=profile_cache,
            fundi_profile_cache=fundi_profile_cache,
            job_cache=job_cache,
            application_cache=application_cache,
            booking_cache=booking_cache,
        )
        context_filters = _message_query_filters(context)
        sent = _fetch_rows(
            admin,
            "messages",
            "*",
            {"sender_id": user.user_id, "recipient_id": participant_id, **context_filters},
        )
        received = _fetch_rows(
            admin,
            "messages",
            "*",
            {"sender_id": participant_id, "recipient_id": user.user_id, **context_filters},
        )
        messages = _merge_messages(sent, received)

        unread_ids = [row["id"] for row in messages if row.get("recipient_id") == user.user_id and not row.get("read_at")]
        if unread_ids:
            read_at = _now_iso()
            for message_id in unread_ids:
                admin.table("messages").update({"read_at": read_at}).eq("id", message_id).execute()
            for row in messages:
                if row.get("id") in unread_ids:
                    row["read_at"] = read_at

        last_message = messages[-1] if messages else None
        thread = _build_thread_summary(
            admin,
            user_id=user.user_id,
            participant_id=participant_id,
            context=context,
            last_message=last_message,
            unread_count=0,
            message_count=len(messages),
            profile_cache=profile_cache,
            fundi_profile_cache=fundi_profile_cache,
        )

        return {"thread": thread, "messages": messages}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to load message thread",
            user_id=user.user_id,
            participant_id=participant_id,
            error=str(exc),
        )
        raise _messages_http_error(exc, default_detail="Failed to fetch this conversation.")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def send_message(body: SendMessageRequest, user: CurrentUser):
    admin = get_admin_client()
    profile_cache: dict[str, dict | None] = {}
    fundi_profile_cache: dict[str, dict | None] = {}
    job_cache: dict[str, dict | None] = {}
    application_cache: dict[str, dict | None] = {}
    booking_cache: dict[str, dict | None] = {}

    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message body cannot be empty")

    try:
        context = _resolve_thread_context(
            admin,
            user=user,
            participant_id=body.participant_id,
            job_id=body.job_id,
            application_id=body.application_id,
            booking_id=body.booking_id,
            profile_cache=profile_cache,
            fundi_profile_cache=fundi_profile_cache,
            job_cache=job_cache,
            application_cache=application_cache,
            booking_cache=booking_cache,
        )
        job = context.get("job") or {}
        application = context.get("application") or {}
        booking = context.get("booking") or {}

        result = admin.table("messages").insert(
            {
                "sender_id": user.user_id,
                "recipient_id": body.participant_id,
                "job_id": job.get("id"),
                "application_id": application.get("id"),
                "booking_id": booking.get("id"),
                "body": text,
            }
        ).execute()
        message = result.data[0]

        sender_profile = _get_profile(admin, user.user_id, profile_cache) or {}
        sender_name = sender_profile.get("full_name") or "Someone"
        await create_notification(
            user_id=body.participant_id,
            type_="message",
            title=f"{sender_name} sent you a message",
            body=_message_preview(text),
            action_url=_message_action_url(context, user.user_id),
            metadata={
                "sender_id": user.user_id,
                "recipient_id": body.participant_id,
                "job_id": job.get("id"),
                "application_id": application.get("id"),
                "booking_id": booking.get("id"),
                "sent_at": _now_iso(),
            },
        )

        return message
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to send message",
            user_id=user.user_id,
            participant_id=body.participant_id,
            error=str(exc),
        )
        raise _messages_http_error(exc, default_detail="Failed to send your message.")
