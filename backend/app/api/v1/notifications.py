from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client

logger = get_logger(__name__)
router = APIRouter()


class NotificationUpdateRequest(BaseModel):
    read: bool = True


def _build_notification_summary(rows: list[dict], unread_messages: int | None = None) -> dict:
    unread_rows = [row for row in rows if not row.get("read")]
    fallback_unread_messages = [
        row for row in unread_rows
        if "message" in str(row.get("type") or "").lower()
    ]
    return {
        "total": len(rows),
        "unread": len(unread_rows),
        "unread_messages": len(fallback_unread_messages) if unread_messages is None else unread_messages,
    }


def _count_unread_messages(admin, user_id: str) -> int | None:
    try:
        result = (
            admin.table("messages")
            .select("id, read_at")
            .eq("recipient_id", user_id)
            .execute()
        )
        rows = result.data or []
        return len([row for row in rows if not row.get("read_at")])
    except Exception as exc:
        logger.warning(
            "Falling back to message notifications for unread inbox count",
            user_id=user_id,
            error=str(exc),
        )
        return None


@router.get("/")
async def list_notifications(user: CurrentUser):
    admin = get_admin_client()
    try:
        result = (
            admin.table("notifications")
            .select("*")
            .eq("user_id", user.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"data": result.data or []}
    except Exception as exc:
        logger.error("Failed to fetch notifications", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch notifications.")


@router.get("/summary")
async def notification_summary(user: CurrentUser):
    admin = get_admin_client()
    try:
        result = (
            admin.table("notifications")
            .select("id, type, read")
            .eq("user_id", user.user_id)
            .execute()
        )
        rows = result.data or []
        unread_messages = _count_unread_messages(admin, user.user_id)
        return _build_notification_summary(rows, unread_messages=unread_messages)
    except Exception as exc:
        logger.error("Failed to fetch notification summary", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch notification summary.")


@router.patch("/{notification_id}")
async def update_notification(
    notification_id: str,
    body: NotificationUpdateRequest,
    user: CurrentUser,
):
    admin = get_admin_client()
    try:
        existing = (
            admin.table("notifications")
            .select("id, user_id, read")
            .eq("id", notification_id)
            .maybe_single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Notification not found")
        if existing.data["user_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Not your notification")

        updated = (
            admin.table("notifications")
            .update({"read": body.read})
            .eq("id", notification_id)
            .execute()
        )
        return updated.data[0] if updated.data else {"id": notification_id, "read": body.read}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to update notification",
            notification_id=notification_id,
            user_id=user.user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to update notification.")


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    user: CurrentUser,
):
    admin = get_admin_client()
    try:
        existing = (
            admin.table("notifications")
            .select("id, user_id, read")
            .eq("id", notification_id)
            .maybe_single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Notification not found")
        if existing.data["user_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Not your notification")
        if not existing.data["read"]:
            raise HTTPException(
                status_code=400,
                detail="Mark this notification as read before deleting it.",
            )

        admin.table("notifications").delete().eq("id", notification_id).execute()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to delete notification",
            notification_id=notification_id,
            user_id=user.user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to delete notification.")


@router.post("/read-all")
async def mark_all_notifications_read(user: CurrentUser):
    admin = get_admin_client()
    try:
        existing = (
            admin.table("notifications")
            .select("id, read")
            .eq("user_id", user.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        unread = [row for row in (existing.data or []) if not row.get("read")]

        if unread:
            admin.table("notifications").update({"read": True}).eq("user_id", user.user_id).execute()

        return {"success": True, "updated": len(unread)}
    except Exception as exc:
        logger.error("Failed to mark notifications read", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update notifications.")
