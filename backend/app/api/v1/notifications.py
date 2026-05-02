from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client

logger = get_logger(__name__)
router = APIRouter()


class NotificationUpdateRequest(BaseModel):
    read: bool = True


def _build_notification_summary(rows: list[dict]) -> dict:
    unread_rows = [row for row in rows if not row.get("read")]
    unread_messages = [
        row for row in unread_rows
        if "message" in str(row.get("type") or "").lower()
    ]
    return {
        "total": len(rows),
        "unread": len(unread_rows),
        "unread_messages": len(unread_messages),
    }


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
        return _build_notification_summary(rows)
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
