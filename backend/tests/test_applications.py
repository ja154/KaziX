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


applications_module = _load_module(
    "test_applications_route_module",
    "app/api/v1/applications.py",
)


class _FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeTableQuery:
    def __init__(self, tables: dict[str, dict[str, dict]], table_name: str) -> None:
        self.tables = tables
        self.table_name = table_name
        self._operation = "select"
        self._filters: dict[str, object] = {}
        self._payload: dict | None = None

    def select(self, _columns: str):
        self._operation = "select"
        return self

    def eq(self, field: str, value):
        self._filters[field] = value
        return self

    def single(self):
        return self

    def update(self, payload: dict):
        self._operation = "update"
        self._payload = dict(payload)
        return self

    def execute(self):
        table = self.tables.setdefault(self.table_name, {})
        rows = [
            row for row in table.values()
            if all(row.get(field) == value for field, value in self._filters.items())
        ]

        if self._operation == "select":
            if len(rows) == 1:
                return _FakeResult(dict(rows[0]))
            return _FakeResult(None)

        if self._operation == "update":
            updated_rows: list[dict] = []
            for row in rows:
                row.update(self._payload or {})
                updated_rows.append(dict(row))
            return _FakeResult(updated_rows)

        raise AssertionError(f"Unexpected operation: {self._operation}")


class _FakeAdminClient:
    def __init__(self, initial_tables: dict[str, dict[str, dict]]) -> None:
        self.tables = initial_tables

    def table(self, table_name: str):
        return _FakeTableQuery(self.tables, table_name)


def _client_user(user_id: str = "client-123"):
    return deps_module.AuthenticatedUser(
        user_id=user_id,
        role="client",
        phone="+254712345678",
    )


@pytest.mark.asyncio
async def test_client_can_shortlist_application_and_mark_job_reviewing(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "applications": {
                "app-1": {
                    "id": "app-1",
                    "job_id": "job-1",
                    "fundi_id": "fundi-1",
                    "status": "pending",
                }
            },
            "jobs": {
                "job-1": {
                    "id": "job-1",
                    "client_id": "client-123",
                    "status": "open",
                    "title": "Install CCTV cameras",
                }
            },
        }
    )
    notifications: list[dict] = []

    async def _fake_notification(**payload):
        notifications.append(payload)
        return payload

    monkeypatch.setattr(applications_module, "get_admin_client", lambda: fake_admin)
    monkeypatch.setattr(applications_module, "create_notification", _fake_notification)

    result = await applications_module.update_application_for_client(
        "app-1",
        applications_module.ClientUpdateApplicationRequest(status="shortlisted"),
        _client_user(),
    )

    assert result["status"] == "shortlisted"
    assert fake_admin.tables["applications"]["app-1"]["status"] == "shortlisted"
    assert fake_admin.tables["jobs"]["job-1"]["status"] == "reviewing"
    assert notifications[0]["user_id"] == "fundi-1"
    assert notifications[0]["metadata"]["status"] == "shortlisted"


@pytest.mark.asyncio
async def test_client_cannot_manage_another_clients_job(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "applications": {
                "app-1": {
                    "id": "app-1",
                    "job_id": "job-1",
                    "fundi_id": "fundi-1",
                    "status": "pending",
                }
            },
            "jobs": {
                "job-1": {
                    "id": "job-1",
                    "client_id": "client-999",
                    "status": "open",
                    "title": "Fix sink",
                }
            },
        }
    )

    async def _fake_notification(**_payload):
        return {}

    monkeypatch.setattr(applications_module, "get_admin_client", lambda: fake_admin)
    monkeypatch.setattr(applications_module, "create_notification", _fake_notification)

    with pytest.raises(HTTPException) as exc:
        await applications_module.update_application_for_client(
            "app-1",
            applications_module.ClientUpdateApplicationRequest(status="rejected"),
            _client_user(),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Not your job"


@pytest.mark.asyncio
async def test_client_cannot_change_withdrawn_application(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "applications": {
                "app-1": {
                    "id": "app-1",
                    "job_id": "job-1",
                    "fundi_id": "fundi-1",
                    "status": "withdrawn",
                }
            },
            "jobs": {
                "job-1": {
                    "id": "job-1",
                    "client_id": "client-123",
                    "status": "reviewing",
                    "title": "Paint a house",
                }
            },
        }
    )

    async def _fake_notification(**_payload):
        return {}

    monkeypatch.setattr(applications_module, "get_admin_client", lambda: fake_admin)
    monkeypatch.setattr(applications_module, "create_notification", _fake_notification)

    with pytest.raises(HTTPException) as exc:
        await applications_module.update_application_for_client(
            "app-1",
            applications_module.ClientUpdateApplicationRequest(status="pending"),
            _client_user(),
        )

    assert exc.value.status_code == 400
    assert "withdrawn" in exc.value.detail
