import importlib.util
from pathlib import Path

import pytest

from app.api import deps as deps_module


def _load_module(module_name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


messages_module = _load_module(
    "test_messages_route_module",
    "app/api/v1/messages.py",
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

    def single(self):
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

    def insert(self, payload: dict):
        self._operation = "insert"
        self._payload = dict(payload)
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
                return _FakeResult(dict(matches[0])) if matches else None
            return _FakeResult([dict(row) for row in matches])

        if self._operation == "update":
            updated = []
            for row in matches:
                row.update(self._payload or {})
                updated.append(dict(row))
            return _FakeResult(updated)

        if self._operation == "insert":
            row = dict(self._payload or {})
            row.setdefault("id", f"{self.table_name}-{len(table) + 1}")
            table.append(row)
            return _FakeResult([dict(row)])

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
async def test_send_message_uses_application_context_and_creates_notification(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "profiles": [
                {"id": "client-1", "role": "client", "full_name": "Client One", "county": "Nairobi", "area": "Westlands"},
                {"id": "fundi-1", "role": "fundi", "full_name": "Fundi One", "county": "Nairobi", "area": "Kilimani"},
            ],
            "jobs": [
                {"id": "job-1", "client_id": "client-1", "title": "Fix sink", "trade": "plumber", "county": "Nairobi", "area": "Westlands", "status": "open", "created_at": "2026-05-01T09:00:00Z"},
            ],
            "applications": [
                {"id": "app-1", "job_id": "job-1", "fundi_id": "fundi-1", "status": "pending", "bid_amount": 800, "created_at": "2026-05-01T09:10:00Z"},
            ],
            "messages": [],
        }
    )
    notifications: list[dict] = []

    async def _fake_notification(**payload):
        notifications.append(payload)
        return payload

    monkeypatch.setattr(messages_module, "get_admin_client", lambda: fake_admin)
    monkeypatch.setattr(messages_module, "create_notification", _fake_notification)

    result = await messages_module.send_message(
        messages_module.SendMessageRequest(
            participant_id="client-1",
            application_id="app-1",
            body="  Habari boss, I can start today.  ",
        ),
        _override_user("fundi", "fundi-1"),
    )

    assert result["recipient_id"] == "client-1"
    assert result["job_id"] == "job-1"
    assert result["application_id"] == "app-1"
    assert result["body"] == "Habari boss, I can start today."
    assert fake_admin.tables["messages"][0]["body"] == "Habari boss, I can start today."
    assert notifications[0]["user_id"] == "client-1"
    assert notifications[0]["type_"] == "message"
    assert "messages.html?participant=fundi-1" in notifications[0]["action_url"]


@pytest.mark.asyncio
async def test_get_message_thread_marks_incoming_messages_as_read(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "profiles": [
                {"id": "client-1", "role": "client", "full_name": "Client One", "county": "Nairobi", "area": "Westlands"},
                {"id": "fundi-1", "role": "fundi", "full_name": "Fundi One", "county": "Nairobi", "area": "Kilimani"},
            ],
            "jobs": [
                {"id": "job-1", "client_id": "client-1", "title": "Fix sink", "trade": "plumber", "county": "Nairobi", "area": "Westlands", "status": "open", "created_at": "2026-05-01T09:00:00Z"},
            ],
            "applications": [
                {"id": "app-1", "job_id": "job-1", "fundi_id": "fundi-1", "status": "pending", "bid_amount": 800, "created_at": "2026-05-01T09:10:00Z"},
            ],
            "messages": [
                {
                    "id": "msg-1",
                    "sender_id": "client-1",
                    "recipient_id": "fundi-1",
                    "job_id": "job-1",
                    "application_id": "app-1",
                    "booking_id": None,
                    "body": "Can you come this afternoon?",
                    "created_at": "2026-05-01T09:30:00Z",
                    "read_at": None,
                }
            ],
        }
    )

    monkeypatch.setattr(messages_module, "get_admin_client", lambda: fake_admin)

    result = await messages_module.get_message_thread(
        _override_user("fundi", "fundi-1"),
        participant_id="client-1",
        application_id="app-1",
    )

    assert result["thread"]["participant_id"] == "client-1"
    assert result["messages"][0]["read_at"] is not None
    assert fake_admin.tables["messages"][0]["read_at"] is not None
    assert result["thread"]["participant_trade"] is None
