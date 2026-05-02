"""
app/services/notifications.py
─────────────────────────────
Handles in-app and SMS notifications.
"""

from app.core.logging import get_logger

logger = get_logger(__name__)


def _normalize_action_url(action_url: str | None) -> str | None:
    value = str(action_url or "").strip()
    if not value:
        return None

    if value.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return value

    path, separator, query = value.partition("?")
    if not path.endswith(".html"):
        return value

    if path.startswith("/pages/"):
        normalized_path = path
    elif path.startswith("/"):
        normalized_path = f"/pages{path}"
    else:
        normalized_path = f"/pages/{path.lstrip('/')}"

    return f"{normalized_path}?{query}" if separator else normalized_path


async def create_notification(
    user_id: str,
    type_: str,
    title: str,
    body: str,
    action_url: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    Creates an in-app notification in the database.
    Will be extended to send SMS via Africa's Talking in future tasks.
    """
    from app.core.supabase import get_admin_client

    admin = get_admin_client()
    data = {
        "user_id":    user_id,
        "type":       type_,
        "title":      title,
        "body":       body,
        "action_url": _normalize_action_url(action_url),
        "metadata":   metadata or {},
        "read":       False,
    }

    try:
        result = admin.table("notifications").insert(data).execute()
        logger.info("Notification created", user_id=user_id, type=type_)
        return result.data[0] if result.data else {}
    except Exception as exc:
        logger.error("Failed to create notification", user_id=user_id, error=str(exc))
        return {}
