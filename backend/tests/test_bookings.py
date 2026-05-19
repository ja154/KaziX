import asyncio
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

from app.api import deps as deps_module


def _load_module(module_name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


bookings_module = _load_module(
    "test_bookings_route_module",
    "app/api/v1/bookings.py",
)


class _FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeTableQuery:
    def __init__(self, rows: list[dict], error: Exception | None = None) -> None:
        self.rows = [dict(row) for row in rows]
        self.error = error
        self._filters: list[tuple[str, str, object]] = []
        self._order_field: str | None = None
        self._order_desc = False

    def select(self, _columns: str):
        return self

    def eq(self, field: str, value):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field: str, values: list[object]):
        self._filters.append(("in", field, list(values)))
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def execute(self):
        if self.error is not None:
            raise self.error

        rows = [dict(row) for row in self.rows]

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

        return _FakeResult(rows)


class _FakeAdminClient:
    def __init__(
        self,
        bookings_rows: list[dict],
        fundi_profile_rows: list[dict] | None = None,
        fundi_profiles_error: Exception | None = None,
    ) -> None:
        self.bookings_rows = bookings_rows
        self.fundi_profile_rows = fundi_profile_rows or []
        self.fundi_profiles_error = fundi_profiles_error

    def table(self, table_name: str):
        if table_name == "bookings":
            return _FakeTableQuery(self.bookings_rows)
        if table_name == "fundi_profiles":
            return _FakeTableQuery(self.fundi_profile_rows, error=self.fundi_profiles_error)
        raise AssertionError(f"Unexpected table requested: {table_name}")


def _override_client_user():
    return deps_module.AuthenticatedUser(
        user_id="client-123",
        role="client",
        phone="+254712345678",
    )


def _create_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(bookings_module.router, prefix="/v1/bookings")
    return test_app


def _list_bookings(*, admin, role: str = "client", status_filter: str | None = None):
    bookings_module.get_admin_client = lambda: admin
    return asyncio.run(
        bookings_module.list_bookings(
            _override_client_user(),
            role=role,
            status_filter=status_filter,
        )
    )


def test_list_bookings_supports_canonical_path_without_redirect() -> None:
    test_app = _create_test_app()
    route_paths = {
        route.path
        for route in test_app.router.routes
        if getattr(route, "endpoint", None) is bookings_module.list_bookings
    }

    assert "/v1/bookings" in route_paths


def test_list_bookings_trailing_slash_path_remains_compatible() -> None:
    test_app = _create_test_app()
    route_paths = {
        route.path
        for route in test_app.router.routes
        if getattr(route, "endpoint", None) is bookings_module.list_bookings
    }

    assert "/v1/bookings/" in route_paths


def test_list_bookings_returns_rows_in_descending_created_order_with_fundi_details() -> None:
    payload = _list_bookings(
        admin=_FakeAdminClient(
            [
                {
                    "id": "booking-newest",
                    "job_id": "job-1",
                    "client_id": "client-123",
                    "fundi_id": "fundi-1",
                    "status": "confirmed",
                    "escrow_status": "pending",
                    "created_at": "2026-05-02T09:00:00Z",
                    "fundi_profile": {
                        "id": "fundi-1",
                        "full_name": "Alice Wanjiku",
                    },
                },
                {
                    "id": "booking-older",
                    "job_id": "job-2",
                    "client_id": "client-123",
                    "fundi_id": "fundi-2",
                    "status": "in_progress",
                    "escrow_status": "held",
                    "created_at": "2026-05-01T09:00:00Z",
                    "fundi_profile": {
                        "id": "fundi-2",
                        "full_name": "Brian Otieno",
                    },
                },
                {
                    "id": "booking-other-client",
                    "job_id": "job-3",
                    "client_id": "client-999",
                    "fundi_id": "fundi-3",
                    "status": "confirmed",
                    "escrow_status": "pending",
                    "created_at": "2026-05-03T09:00:00Z",
                },
            ],
            [
                {
                    "id": "fundi-1",
                    "trade": "plumber",
                    "rating_avg": 4.8,
                    "jobs_completed": 17,
                    "experience_years": 6,
                    "kyc_status": "approved",
                    "is_available": True,
                },
                {
                    "id": "fundi-2",
                    "trade": "electrician",
                    "rating_avg": 4.4,
                    "jobs_completed": 9,
                    "experience_years": 4,
                    "kyc_status": "approved",
                    "is_available": False,
                },
            ],
        )
    )

    assert [booking["id"] for booking in payload] == [
        "booking-newest",
        "booking-older",
    ]
    assert payload[0]["fundi_profile"] == {
        "id": "fundi-1",
        "full_name": "Alice Wanjiku",
    }
    assert payload[0]["fundi_details"] == {
        "trade": "plumber",
        "rating_avg": 4.8,
        "jobs_completed": 17,
        "experience_years": 6,
        "kyc_status": "approved",
        "is_available": True,
    }


def test_list_bookings_returns_null_fundi_details_when_profile_row_missing() -> None:
    payload = _list_bookings(
        admin=_FakeAdminClient(
            [
                {
                    "id": "booking-1",
                    "job_id": "job-1",
                    "client_id": "client-123",
                    "fundi_id": "fundi-missing",
                    "status": "confirmed",
                    "escrow_status": "pending",
                    "created_at": "2026-05-02T09:00:00Z",
                    "fundi_profile": {
                        "id": "fundi-missing",
                        "full_name": "Missing Fundi",
                    },
                }
            ]
        )
    )

    assert payload[0]["fundi_profile"] == {
        "id": "fundi-missing",
        "full_name": "Missing Fundi",
    }
    assert payload[0]["fundi_details"] is None


def test_list_bookings_returns_base_rows_when_fundi_enrichment_fails() -> None:
    payload = _list_bookings(
        admin=_FakeAdminClient(
            [
                {
                    "id": "booking-1",
                    "job_id": "job-1",
                    "client_id": "client-123",
                    "fundi_id": "fundi-1",
                    "status": "confirmed",
                    "escrow_status": "pending",
                    "created_at": "2026-05-02T09:00:00Z",
                    "fundi_profile": {
                        "id": "fundi-1",
                        "full_name": "Alice Wanjiku",
                    },
                }
            ],
            fundi_profiles_error=RuntimeError("fundi profile lookup failed"),
        )
    )

    assert payload[0]["id"] == "booking-1"
    assert payload[0]["fundi_profile"] == {
        "id": "fundi-1",
        "full_name": "Alice Wanjiku",
    }
    assert payload[0]["fundi_details"] is None


def test_list_bookings_rejects_role_mismatch() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _list_bookings(admin=_FakeAdminClient([]), role="fundi")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You can only view bookings for your own account role."
