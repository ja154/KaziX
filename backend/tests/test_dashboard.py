from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from app.api import deps as deps_module


def _load_module(module_name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


dashboard_module = _load_module(
    "test_dashboard_route_module",
    "app/api/v1/dashboard.py",
)


class _FakeResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeTableQuery:
    def __init__(self, tables: dict[str, list[dict]], table_name: str) -> None:
        self.tables = tables
        self.table_name = table_name
        self._filters: list[tuple[str, str, Any]] = []
        self._order_field: str | None = None
        self._order_desc = False
        self._single = False

    def select(self, _columns: str):
        return self

    def eq(self, field: str, value: Any):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field: str, values: list[Any]):
        self._filters.append(("in", field, list(values)))
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        rows = [dict(row) for row in self.tables.get(self.table_name, [])]

        for operation, field, value in self._filters:
            if operation == "eq":
                rows = [row for row in rows if row.get(field) == value]
            elif operation == "in":
                allowed = set(value)
                rows = [row for row in rows if row.get(field) in allowed]

        if self._order_field:
            rows.sort(
                key=lambda row: row.get(self._order_field) or "",
                reverse=self._order_desc,
            )

        if self._single:
            return _FakeResult(rows[0] if rows else None)
        return _FakeResult(rows)


class _FakeAdminClient:
    def __init__(self, tables: dict[str, list[dict]] | None = None) -> None:
        self.tables = tables or {}

    def table(self, table_name: str):
        return _FakeTableQuery(self.tables, table_name)


def _override_user(role: str, user_id: str):
    return deps_module.AuthenticatedUser(
        user_id=user_id,
        role=role,
        phone="+254712345678",
    )


@pytest.mark.asyncio
async def test_client_dashboard_state_returns_zeroed_metrics_for_fresh_account(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "jobs": [],
            "applications": [],
            "bookings": [],
            "transactions": [],
        }
    )

    monkeypatch.setattr(dashboard_module, "get_admin_client", lambda: fake_admin)

    payload = await dashboard_module.get_dashboard_state(_override_user("client", "client-1"))

    assert payload["role"] == "client"
    assert payload["nav"] == {
        "jobs": 0,
        "applications": 0,
        "hires": 0,
        "saved_workers": None,
        "messages": None,
    }
    assert payload["client"]["jobs"]["total"] == 0
    assert payload["client"]["payments"]["total_spent"] == 0
    assert payload["client"]["payments"]["this_month"] == 0
    assert payload["client"]["recent_jobs"] == []
    assert len(payload["client"]["monthly_spend"]) == 6


@pytest.mark.asyncio
async def test_client_dashboard_state_summarizes_jobs_applications_and_spend(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "jobs": [
                {
                    "id": "job-1",
                    "client_id": "client-1",
                    "title": "Fix leaking pipe",
                    "trade": "plumber",
                    "county": "Nairobi",
                    "area": "Westlands",
                    "status": "open",
                    "created_at": "2026-05-01T10:00:00Z",
                },
                {
                    "id": "job-2",
                    "client_id": "client-1",
                    "title": "Paint living room",
                    "trade": "painter",
                    "county": "Nairobi",
                    "area": "Kilimani",
                    "status": "completed",
                    "created_at": "2026-04-20T10:00:00Z",
                },
            ],
            "applications": [
                {"id": "app-1", "job_id": "job-1", "status": "pending", "created_at": "2026-05-01T11:00:00Z"},
                {"id": "app-2", "job_id": "job-1", "status": "withdrawn", "created_at": "2026-05-01T12:00:00Z"},
                {"id": "app-3", "job_id": "job-2", "status": "hired", "created_at": "2026-04-21T09:00:00Z"},
            ],
            "bookings": [
                {
                    "id": "booking-1",
                    "job_id": "job-1",
                    "client_id": "client-1",
                    "fundi_id": "fundi-1",
                    "agreed_amount": 2500,
                    "status": "in_progress",
                    "escrow_status": "held",
                    "created_at": "2026-05-01T13:00:00Z",
                },
                {
                    "id": "booking-2",
                    "job_id": "job-2",
                    "client_id": "client-1",
                    "fundi_id": "fundi-2",
                    "agreed_amount": 1000,
                    "status": "completed",
                    "escrow_status": "released",
                    "created_at": "2026-04-21T10:00:00Z",
                },
            ],
            "transactions": [
                {
                    "id": "tx-1",
                    "booking_id": "booking-1",
                    "type": "escrow_in",
                    "amount": 2500,
                    "status": "confirmed",
                    "mpesa_ref": "ABC123",
                    "created_at": "2026-05-01T13:05:00Z",
                },
                {
                    "id": "tx-2",
                    "booking_id": "booking-2",
                    "type": "escrow_in",
                    "amount": 1000,
                    "status": "confirmed",
                    "mpesa_ref": "DEF456",
                    "created_at": "2026-04-21T10:05:00Z",
                },
                {
                    "id": "tx-3",
                    "booking_id": "booking-2",
                    "type": "refund",
                    "amount": 200,
                    "status": "confirmed",
                    "mpesa_ref": "REF200",
                    "created_at": "2026-05-01T14:00:00Z",
                },
            ],
        }
    )

    monkeypatch.setattr(dashboard_module, "get_admin_client", lambda: fake_admin)

    payload = await dashboard_module.get_dashboard_state(_override_user("client", "client-1"))

    assert payload["nav"]["jobs"] == 2
    assert payload["nav"]["applications"] == 2
    assert payload["nav"]["hires"] == 1
    assert payload["client"]["jobs"]["open"] == 1
    assert payload["client"]["jobs"]["completed"] == 1
    assert payload["client"]["applications"]["pending"] == 1
    assert payload["client"]["applications"]["withdrawn"] == 1
    assert payload["client"]["payments"]["total_spent"] == 3300
    assert payload["client"]["payments"]["in_escrow"] == 2500
    assert payload["client"]["payments"]["refunded_total"] == 200
    assert payload["client"]["payments"]["avg_job_value"] == 1750
    assert payload["client"]["recent_jobs"][0]["application_count"] == 1
    assert {item["title"] for item in payload["client"]["recent_transactions"]} == {
        "Fix leaking pipe",
        "Paint living room",
    }


@pytest.mark.asyncio
async def test_fundi_dashboard_state_summarizes_alerts_contracts_and_earnings(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        {
            "fundi_profiles": [
                {
                    "id": "fundi-1",
                    "trade": "plumber",
                    "rating_avg": 4.9,
                    "jobs_completed": 9,
                    "is_available": False,
                }
            ],
            "applications": [
                {"id": "app-1", "job_id": "job-1", "status": "pending", "fundi_id": "fundi-1", "created_at": "2026-05-01T08:00:00Z"},
                {"id": "app-2", "job_id": "job-2", "status": "withdrawn", "fundi_id": "fundi-1", "created_at": "2026-04-30T08:00:00Z"},
                {"id": "app-3", "job_id": "job-3", "status": "hired", "fundi_id": "fundi-1", "created_at": "2026-04-20T08:00:00Z"},
            ],
            "bookings": [
                {
                    "id": "booking-1",
                    "job_id": "job-1",
                    "client_id": "client-1",
                    "fundi_id": "fundi-1",
                    "agreed_amount": 3000,
                    "status": "confirmed",
                    "escrow_status": "held",
                    "created_at": "2026-05-01T09:00:00Z",
                },
                {
                    "id": "booking-2",
                    "job_id": "job-3",
                    "client_id": "client-2",
                    "fundi_id": "fundi-1",
                    "agreed_amount": 4000,
                    "status": "completed",
                    "escrow_status": "released",
                    "escrow_released_at": "2026-05-01T10:00:00Z",
                    "updated_at": "2026-05-01T10:00:00Z",
                    "created_at": "2026-04-20T09:00:00Z",
                },
            ],
            "jobs": [
                {
                    "id": "job-1",
                    "client_id": "client-1",
                    "title": "Emergency pipe repair",
                    "trade": "plumber",
                    "county": "Nairobi",
                    "area": "Westlands",
                    "budget_min": 1500,
                    "budget_max": 3000,
                    "urgency": "urgent",
                    "status": "open",
                    "created_at": "2026-05-01T07:00:00Z",
                },
                {
                    "id": "job-2",
                    "client_id": "client-2",
                    "title": "Bathroom fitting",
                    "trade": "plumber",
                    "county": "Nairobi",
                    "area": "Kilimani",
                    "budget_min": 2500,
                    "budget_max": 5000,
                    "urgency": "flexible",
                    "status": "open",
                    "created_at": "2026-04-30T07:00:00Z",
                },
                {
                    "id": "job-3",
                    "client_id": "client-3",
                    "title": "Install water heater",
                    "trade": "plumber",
                    "county": "Nairobi",
                    "area": "Karen",
                    "budget_min": 4000,
                    "budget_max": 6000,
                    "urgency": "flexible",
                    "status": "completed",
                    "created_at": "2026-04-20T07:00:00Z",
                },
                {
                    "id": "job-4",
                    "client_id": "fundi-1",
                    "title": "Should be hidden",
                    "trade": "plumber",
                    "county": "Nairobi",
                    "area": "CBD",
                    "budget_min": 1000,
                    "budget_max": 2000,
                    "urgency": "urgent",
                    "status": "open",
                    "created_at": "2026-05-01T11:00:00Z",
                },
                {
                    "id": "job-5",
                    "client_id": "client-9",
                    "title": "Electrical job",
                    "trade": "electrician",
                    "county": "Nairobi",
                    "area": "South B",
                    "budget_min": 3000,
                    "budget_max": 4500,
                    "urgency": "flexible",
                    "status": "open",
                    "created_at": "2026-05-01T06:00:00Z",
                },
            ],
        }
    )

    monkeypatch.setattr(dashboard_module, "get_admin_client", lambda: fake_admin)

    payload = await dashboard_module.get_dashboard_state(_override_user("fundi", "fundi-1"))

    assert payload["role"] == "fundi"
    assert payload["nav"]["find_jobs"] == 2
    assert payload["nav"]["applications"] == 2
    assert payload["nav"]["contracts"] == 1
    assert payload["fundi"]["availability"]["is_available"] is False
    assert payload["fundi"]["applications"]["pending"] == 1
    assert payload["fundi"]["contracts"]["in_escrow"] == 3000
    assert payload["fundi"]["earnings"]["gross_released_total"] == 4000
    assert payload["fundi"]["earnings"]["platform_fees_total"] == 400
    assert payload["fundi"]["earnings"]["net_released_total"] == 3600
    assert payload["fundi"]["rating"]["average"] == 4.9
    assert payload["fundi"]["recent_alerts"][0]["title"] == "Emergency pipe repair"
