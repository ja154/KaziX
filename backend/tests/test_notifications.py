import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import deps as deps_module


def _load_module(module_name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


notifications_module = _load_module(
    "test_notifications_route_module",
    "app/api/v1/notifications.py",
)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTableQuery:
    def __init__(self, tables: dict[str, list[dict]], table_name: str) -> None:
        self.tables = tables
        self.table_name = table_name
        self._operation = "select"
        self._filters: list[tuple[str, object]] = []
        self._payload: dict | None = None
        self._single = False
        self._order_field: str | None = None
        self._order_desc = False

    def select(self, _columns: str):
        self._operation = "select"
        return self

    def eq(self, field: str, value):
        self._filters.append((field, value))
        return self

    def maybe_single(self):
        self._single = True
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def update(self, payload: dict):
        self._operation = "update"
        self._payload = dict(payload)
        return self

    def delete(self):
        self._operation = "delete"
        return self

    def execute(self):
        table = self.tables.setdefault(self.table_name, [])
        matches = [
          row for row in table
          if all(row.get(field) == value for field, value in self._filters)
        ]

        if self._order_field:
            matches = sorted(
                matches,
                key=lambda row: row.get(self._order_field) or "",
                reverse=self._order_desc,
            )

        if self._operation == "select":
            if self._single:
                return _FakeResult(dict(matches[0]) if matches else None)
            return _FakeResult([dict(row) for row in matches])

        if self._operation == "update":
            updated = []
            for row in matches:
                row.update(self._payload or {})
                updated.append(dict(row))
            return _FakeResult(updated)

        if self._operation == "delete":
            deleted = [dict(row) for row in matches]
            self.tables[self.table_name] = [
                row for row in table
                if not all(row.get(field) == value for field, value in self._filters)
            ]
            return _FakeResult(deleted)

        raise AssertionError(f"Unsupported operation: {self._operation}")


class _FakeAdminClient:
    def __init__(self, tables: dict[str, list[dict]]) -> None:
        self.tables = tables

    def table(self, table_name: str):
        return _FakeTableQuery(self.tables, table_name)


def _override_user(role: str, user_id: str):
    return deps_module.AuthenticatedUser(
        user_id=user_id,
        role=role,
        phone="+254712345678",
    )


@pytest.mark.asyncio
async def test_list_notifications_returns_only_current_user_rows(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "client-1", "title": "Newest", "read": False, "created_at": "2026-05-01T10:00:00Z"},
                {"id": "n-2", "user_id": "client-1", "title": "Older", "read": True, "created_at": "2026-05-01T09:00:00Z"},
                {"id": "n-3", "user_id": "other-user", "title": "Ignore", "read": False, "created_at": "2026-05-01T11:00:00Z"},
            ]
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    result = await notifications_module.list_notifications(_override_user("client", "client-1"))

    assert [item["id"] for item in result["data"]] == ["n-1", "n-2"]


@pytest.mark.asyncio
async def test_notification_summary_counts_unread_and_message_notifications(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "client-1", "type": "message", "read": False, "created_at": "2026-05-01T10:00:00Z"},
                {"id": "n-2", "user_id": "client-1", "type": "application", "read": False, "created_at": "2026-05-01T09:00:00Z"},
                {"id": "n-3", "user_id": "client-1", "type": "message", "read": True, "created_at": "2026-05-01T08:00:00Z"},
                {"id": "n-4", "user_id": "other-user", "type": "message", "read": False, "created_at": "2026-05-01T07:00:00Z"},
            ],
            "messages": [
                {"id": "m-1", "recipient_id": "client-1", "read_at": None, "created_at": "2026-05-01T10:01:00Z"},
                {"id": "m-2", "recipient_id": "client-1", "read_at": "2026-05-01T10:02:00Z", "created_at": "2026-05-01T10:00:00Z"},
                {"id": "m-3", "recipient_id": "other-user", "read_at": None, "created_at": "2026-05-01T09:59:00Z"},
            ],
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    result = await notifications_module.notification_summary(_override_user("client", "client-1"))

    assert result == {
        "total": 3,
        "unread": 2,
        "unread_messages": 1,
    }


@pytest.mark.asyncio
async def test_mark_all_notifications_read_updates_unread_rows(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "client-1", "title": "One", "read": False, "created_at": "2026-05-01T10:00:00Z"},
                {"id": "n-2", "user_id": "client-1", "title": "Two", "read": False, "created_at": "2026-05-01T09:00:00Z"},
                {"id": "n-3", "user_id": "other-user", "title": "Ignore", "read": False, "created_at": "2026-05-01T08:00:00Z"},
            ]
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    result = await notifications_module.mark_all_notifications_read(_override_user("client", "client-1"))

    assert result == {"success": True, "updated": 2}
    assert all(item["read"] for item in fake_admin.tables["notifications"] if item["user_id"] == "client-1")
    assert fake_admin.tables["notifications"][2]["read"] is False


@pytest.mark.asyncio
async def test_user_cannot_update_someone_elses_notification(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "other-user", "title": "Nope", "read": False, "created_at": "2026-05-01T10:00:00Z"},
            ]
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    with pytest.raises(HTTPException) as exc:
        await notifications_module.update_notification(
            "n-1",
            notifications_module.NotificationUpdateRequest(read=True),
            _override_user("client", "client-1"),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_notification_removes_read_notification(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "client-1", "title": "Read", "read": True, "created_at": "2026-05-01T10:00:00Z"},
                {"id": "n-2", "user_id": "client-1", "title": "Keep", "read": False, "created_at": "2026-05-01T09:00:00Z"},
            ]
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    response = await notifications_module.delete_notification(
        "n-1",
        _override_user("client", "client-1"),
    )

    assert response.status_code == 204
    assert [item["id"] for item in fake_admin.tables["notifications"]] == ["n-2"]


@pytest.mark.asyncio
async def test_delete_notification_rejects_unread_notification(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "client-1", "title": "Unread", "read": False, "created_at": "2026-05-01T10:00:00Z"},
            ]
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    with pytest.raises(HTTPException) as exc:
        await notifications_module.delete_notification(
            "n-1",
            _override_user("client", "client-1"),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Mark this notification as read before deleting it."
    assert [item["id"] for item in fake_admin.tables["notifications"]] == ["n-1"]


@pytest.mark.asyncio
async def test_user_cannot_delete_someone_elses_notification(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "notifications": [
                {"id": "n-1", "user_id": "other-user", "title": "Nope", "read": True, "created_at": "2026-05-01T10:00:00Z"},
            ]
        }
    )

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    with pytest.raises(HTTPException) as exc:
        await notifications_module.delete_notification(
            "n-1",
            _override_user("client", "client-1"),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_notification_returns_404_when_missing(monkeypatch) -> None:
    fake_admin = _FakeAdminClient({"notifications": []})

    monkeypatch.setattr(notifications_module, "get_admin_client", lambda: fake_admin)

    with pytest.raises(HTTPException) as exc:
        await notifications_module.delete_notification(
            "missing",
            _override_user("client", "client-1"),
        )

    assert exc.value.status_code == 404
