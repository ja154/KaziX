from types import SimpleNamespace

import httpx
import pytest

from app.api import deps as deps_module
from app.api.v1 import jobs as jobs_module
from app.main import app


class _FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeJobsQuery:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = [dict(row) for row in rows]
        self._filters: dict[str, object] = {}
        self._range: tuple[int, int] | None = None
        self._order_field = "created_at"
        self._order_desc = False

    def select(self, _columns: str):
        return self

    def eq(self, field: str, value):
        self._filters[field] = value
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def single(self):
        return self

    def execute(self):
        rows = [
            dict(row)
            for row in self.rows
            if all(row.get(field) == value for field, value in self._filters.items())
        ]
        rows.sort(key=lambda row: row.get(self._order_field) or "", reverse=self._order_desc)

        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]

        return _FakeResult(rows)


class _FakeAdminClient:
    def __init__(self, jobs_rows: list[dict]) -> None:
        self.jobs_rows = jobs_rows

    def table(self, table_name: str):
        if table_name != "jobs":
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _FakeJobsQuery(self.jobs_rows)


def _override_current_user():
    return deps_module.AuthenticatedUser(
        user_id="client-123",
        role="client",
        phone="+254712345678",
    )


@pytest.mark.asyncio
async def test_list_my_jobs_returns_only_authenticated_client_jobs(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        [
            {
                "id": "job-new",
                "client_id": "client-123",
                "title": "Install lights",
                "description": "Install new outdoor security lights around the compound.",
                "trade": "electrician",
                "county": "Nairobi",
                "area": "Kilimani",
                "status": "open",
                "created_at": "2026-05-01T12:00:00Z",
            },
            {
                "id": "job-old",
                "client_id": "client-123",
                "title": "Fix gate lock",
                "description": "Repair the front gate lock and align the latch properly.",
                "trade": "carpenter",
                "county": "Nairobi",
                "area": "Lavington",
                "status": "cancelled",
                "created_at": "2026-04-29T08:00:00Z",
            },
            {
                "id": "job-other-client",
                "client_id": "client-999",
                "title": "Should not leak through",
                "description": "This job belongs to a different client and must stay hidden.",
                "trade": "plumber",
                "county": "Nairobi",
                "area": "Westlands",
                "status": "open",
                "created_at": "2026-05-01T14:00:00Z",
            },
        ]
    )

    monkeypatch.setattr(jobs_module, "get_admin_client", lambda: fake_admin)
    app.dependency_overrides[deps_module.get_current_user] = _override_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/jobs/mine")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [job["id"] for job in payload["data"]] == ["job-new", "job-old"]


@pytest.mark.asyncio
async def test_public_job_list_exposes_description_for_worker_cards(monkeypatch) -> None:
    fake_anon = SimpleNamespace(
        table=lambda table_name: _FakeJobsQuery(
            [
                {
                    "id": "job-123",
                    "title": "Install CCTV",
                    "description": "Install four CCTV cameras and set up the recording unit.",
                    "trade": "electrician",
                    "county": "Nairobi",
                    "area": "Kilimani",
                    "budget_min": 1500,
                    "budget_max": 5000,
                    "payment_type": "fixed",
                    "urgency": "urgent",
                    "preferred_date": "2026-05-03",
                    "materials_provided": False,
                    "status": "open",
                    "expires_at": None,
                    "created_at": "2026-05-01T12:00:00Z",
                    "profiles": {"full_name": "Jane Client", "avatar_url": None},
                }
            ]
        )
    )

    monkeypatch.setattr(jobs_module, "get_anon_client", lambda: fake_anon)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/jobs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["description"] == "Install four CCTV cameras and set up the recording unit."
