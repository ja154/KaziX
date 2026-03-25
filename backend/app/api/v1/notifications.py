"""
app/api/v1/notifications.py
───────────────────────────
Notification inbox endpoints.

GET   /v1/notifications            → list current user's notifications
PATCH /v1/notifications/{id}/read  → mark a notification as read
"""

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.core.supabase import get_admin_client

logger = get_logger(__name__)
router = APIRouter()


@router.get("/")
async def list_notifications(
    user: CurrentUser,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
):
    """
    Returns notifications for the authenticated user.
    Ordered newest-first.
    """
    admin = get_admin_client()
    try:
        query = (
            admin.table("notifications")
            .select("id, type, title, body, action_url, is_read, created_at")
            .eq("user_id", user.user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if unread_only:
            query = query.eq("is_read", False)

        result = query.execute()
        rows = result.data or []
        return {"data": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Notification listing failed", user_id=user.user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch notifications.")


@router.patch("/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: CurrentUser):
    """
    Marks one notification as read if it belongs to the authenticated user.
    """
    admin = get_admin_client()
    try:
        existing = (
            admin.table("notifications")
            .select("id, is_read")
            .eq("id", notification_id)
            .eq("user_id", user.user_id)
            .maybe_single()
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Notification not found")

        if existing.data.get("is_read"):
            return {"success": True, "notification_id": notification_id, "is_read": True}

        updated = (
            admin.table("notifications")
            .update({"is_read": True})
            .eq("id", notification_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        row = updated.data[0] if updated.data else {"id": notification_id, "is_read": True}
        return {"success": True, "notification": row}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Mark-notification-read failed",
            user_id=user.user_id,
            notification_id=notification_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to update notification.")
