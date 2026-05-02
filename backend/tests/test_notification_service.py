import pytest

from app.services import notifications as notifications_service


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTableQuery:
    def __init__(self, tables: dict[str, list[dict]], table_name: str) -> None:
        self.tables = tables
        self.table_name = table_name
        self._payload: dict | None = None

    def insert(self, payload: dict):
        self._payload = dict(payload)
        return self

    def execute(self):
        table = self.tables.setdefault(self.table_name, [])
        row = dict(self._payload or {})
        row.setdefault("id", f"{self.table_name}-{len(table) + 1}")
        table.append(row)
        return _FakeResult([dict(row)])


class _FakeAdminClient:
    def __init__(self, tables: dict[str, list[dict]] | None = None) -> None:
        self.tables = tables or {}

    def table(self, table_name: str):
        return _FakeTableQuery(self.tables, table_name)


@pytest.mark.asyncio
async def test_create_notification_normalizes_html_action_urls(monkeypatch) -> None:
    fake_admin = _FakeAdminClient()

    monkeypatch.setattr("app.core.supabase.get_admin_client", lambda: fake_admin)

    result = await notifications_service.create_notification(
        user_id="client-1",
        type_="message",
        title="New message",
        body="Hello",
        action_url="/messages.html?participant=fundi-1&job=job-1",
    )

    assert result["action_url"] == "/pages/messages.html?participant=fundi-1&job=job-1"
    assert fake_admin.tables["notifications"][0]["action_url"] == "/pages/messages.html?participant=fundi-1&job=job-1"
