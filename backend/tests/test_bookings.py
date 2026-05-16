import httpx
import pytest

from app.api import deps as deps_module
from app.api.v1 import bookings as bookings_module
from app.main import app


class _FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeBookingsQuery:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = [dict(row) for row in rows]
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
    def __init__(self, bookings_rows: list[dict]) -> None:
        self.bookings_rows = bookings_rows

    def table(self, table_name: str):
        if table_name != "bookings":
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _FakeBookingsQuery(self.bookings_rows)


def _override_client_user():
    return deps_module.AuthenticatedUser(
        user_id="client-123",
        role="client",
        phone="+254712345678",
    )


@pytest.mark.asyncio
async def test_list_bookings_supports_canonical_path_without_redirect(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        [
            {
                "id": "booking-newest",
                "job_id": "job-1",
                "client_id": "client-123",
                "fundi_id": "fundi-1",
                "status": "confirmed",
                "escrow_status": "pending",
                "created_at": "2026-05-02T09:00:00Z",
            },
            {
                "id": "booking-older",
                "job_id": "job-2",
                "client_id": "client-123",
                "fundi_id": "fundi-2",
                "status": "in_progress",
                "escrow_status": "held",
                "created_at": "2026-05-01T09:00:00Z",
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
        ]
    )

    monkeypatch.setattr(bookings_module, "get_admin_client", lambda: fake_admin)
    app.dependency_overrides[deps_module.get_current_user] = _override_client_user

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/bookings", params={"role": "client"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [booking["id"] for booking in response.json()] == [
        "booking-newest",
        "booking-older",
    ]


@pytest.mark.asyncio
async def test_list_bookings_trailing_slash_path_remains_compatible(monkeypatch) -> None:
    fake_admin = _FakeAdminClient(
        [
            {
                "id": "booking-1",
                "job_id": "job-1",
                "client_id": "client-123",
                "fundi_id": "fundi-1",
                "status": "confirmed",
                "escrow_status": "pending",
                "created_at": "2026-05-02T09:00:00Z",
            }
        ]
    )

    monkeypatch.setattr(bookings_module, "get_admin_client", lambda: fake_admin)
    app.dependency_overrides[deps_module.get_current_user] = _override_client_user

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            canonical_response = await client.get("/v1/bookings", params={"role": "client"})
            compatibility_response = await client.get("/v1/bookings/", params={"role": "client"})
    finally:
        app.dependency_overrides.clear()

    assert canonical_response.status_code == 200
    assert compatibility_response.status_code == 200
    assert compatibility_response.json() == canonical_response.json()


@pytest.mark.asyncio
async def test_list_bookings_rejects_role_mismatch(monkeypatch) -> None:
    fake_admin = _FakeAdminClient([])

    monkeypatch.setattr(bookings_module, "get_admin_client", lambda: fake_admin)
    app.dependency_overrides[deps_module.get_current_user] = _override_client_user

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/v1/bookings", params={"role": "fundi"})
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    message = payload.get("detail") or payload.get("message")

    assert response.status_code == 403
    assert message == "You can only view bookings for your own account role."
