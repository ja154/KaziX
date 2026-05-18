import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api import deps as deps_module


def _load_module(module_name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


jobs_module = _load_module(
    "test_jobs_route_module",
    "app/api/v1/jobs.py",
)

app = FastAPI()
app.include_router(jobs_module.router, prefix="/v1/jobs")


class _FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeProfilesQuery:
    def __init__(self, profile: dict | None) -> None:
        self.profile = dict(profile) if profile else None
        self._filters: dict[str, object] = {}

    def select(self, _columns: str):
        return self

    def eq(self, field: str, value):
        self._filters[field] = value
        return self

    def single(self):
        return self

    def execute(self):
        if self.profile and all(self.profile.get(field) == value for field, value in self._filters.items()):
            return _FakeResult(dict(self.profile))
        return _FakeResult(None)


class _FakeJobsQuery:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self._filters: dict[str, object] = {}
        self._range: tuple[int, int] | None = None
        self._order_field = "created_at"
        self._order_desc = False
        self._insert_payload: dict | None = None

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

    def insert(self, payload: dict):
        self._insert_payload = dict(payload)
        return self

    def single(self):
        return self

    def execute(self):
        if self._insert_payload is not None:
            row = dict(self._insert_payload)
            row.setdefault("id", f"job-{len(self.rows) + 1}")
            self.rows.append(row)
            self._insert_payload = None
            return _FakeResult([dict(row)])

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


class _FakeProfilesClient:
    def __init__(self, profile: dict | None) -> None:
        self.profile = profile

    def table(self, table_name: str):
        if table_name != "profiles":
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _FakeProfilesQuery(self.profile)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-access-token"}


def _client_profile() -> dict[str, object]:
    return {
        "id": "client-123",
        "role": "client",
        "phone": "+254712345678",
        "is_suspended": False,
    }


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
    fake_profiles = _FakeProfilesClient(_client_profile())

    monkeypatch.setattr(jobs_module, "get_user_client", lambda _token: fake_admin)
    monkeypatch.setattr(deps_module, "_decode_user_id", lambda _credentials: "client-123")
    monkeypatch.setattr(deps_module, "get_admin_client", lambda: fake_profiles)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/jobs/mine", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [job["id"] for job in payload["data"]] == ["job-new", "job-old"]


@pytest.mark.asyncio
async def test_jobs_collection_paths_do_not_redirect(monkeypatch) -> None:
    fake_rows = [
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
    fake_anon = SimpleNamespace(table=lambda table_name: _FakeJobsQuery(fake_rows))

    monkeypatch.setattr(jobs_module, "get_anon_client", lambda: fake_anon)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for path in ("/v1/jobs", "/v1/jobs/"):
            response = await client.get(path, follow_redirects=False)
            assert response.status_code == 200
            assert response.headers.get("location") is None


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


@pytest.mark.asyncio
async def test_create_job_collection_paths_do_not_redirect(monkeypatch) -> None:
    inserted_rows: list[dict] = []
    fake_user_client = _FakeAdminClient(inserted_rows)
    fake_profiles = _FakeProfilesClient(_client_profile())

    monkeypatch.setattr(jobs_module, "get_user_client", lambda _token: fake_user_client)
    monkeypatch.setattr(deps_module, "_decode_user_id", lambda _credentials: "client-123")
    monkeypatch.setattr(deps_module, "get_admin_client", lambda: fake_profiles)

    job_payload = {
        "title": "Install security lights",
        "description": "Install two outdoor security lights and check the existing wiring.",
        "trade": "electrician",
        "county": "Nairobi",
        "area": "Kilimani",
        "street": None,
        "budget_min": 1500,
        "budget_max": 5000,
        "payment_type": "fixed",
        "urgency": "flexible",
        "preferred_date": "2026-05-03",
        "preferred_time": "Morning (7am - 12pm)",
        "materials_provided": False,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for path in ("/v1/jobs", "/v1/jobs/"):
            response = await client.post(
                path,
                json=job_payload,
                headers=_auth_headers(),
                follow_redirects=False,
            )
            assert response.status_code == 201
            assert response.headers.get("location") is None
            created_job = response.json()
            assert created_job["client_id"] == "client-123"
            assert created_job["status"] == "open"
