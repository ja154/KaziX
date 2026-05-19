import re
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from jose import jwt

from app.api import deps as deps_module
from app.api.v1 import profiles as profiles_module
from app.main import app


class _FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeTableQuery:
    def __init__(self, tables: dict[str, dict[str, dict]], table_name: str) -> None:
        self.tables = tables
        self.table_name = table_name
        self._operation = None
        self._payload = None
        self._filters: dict[str, str] = {}

    def select(self, _columns: str):
        self._operation = "select"
        return self

    def eq(self, field: str, value: str):
        self._filters[field] = value
        return self

    def single(self):
        return self

    def maybe_single(self):
        return self

    def insert(self, payload: dict):
        self._operation = "insert"
        self._payload = dict(payload)
        return self

    def execute(self):
        table = self.tables.setdefault(self.table_name, {})

        if self._operation == "select":
            row = table.get(self._filters.get("id"))
            return _FakeResult(dict(row) if row else None)

        if self._operation == "insert":
            row = dict(self._payload)
            table[row["id"]] = row
            return _FakeResult([row])

        raise AssertionError(f"Unexpected operation: {self._operation}")


class _FakeAdminClient:
    def __init__(self, initial_tables: dict[str, dict[str, dict]] | None = None) -> None:
        self.tables = initial_tables or {}

    def table(self, table_name: str):
        return _FakeTableQuery(self.tables, table_name)


class _FakeAuthLookupClient:
    def __init__(self, *, user_id: str, email: str | None = None, phone: str | None = None) -> None:
        self.auth = SimpleNamespace(
            get_user=lambda jwt=None: SimpleNamespace(
                user=SimpleNamespace(id=user_id, email=email, phone=phone)
            )
        )


class _FakeSearchResult:
    def __init__(self, data, count: int) -> None:
        self.data = data
        self.count = count


class _FakeSearchQuery:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self._filters: list[tuple[str, str, object]] = []
        self._order_field: str | None = None
        self._order_desc = False
        self._range: tuple[int, int] | None = None
        self.selected_columns: str | None = None

    def select(self, columns: str, count: str | None = None):
        self.selected_columns = columns
        return self

    def ilike(self, field: str, pattern: str):
        self._filters.append(("ilike", field, pattern))
        return self

    def or_(self, filters: str, reference_table: str | None = None):
        self._filters.append(("or", reference_table or "", filters))
        return self

    def eq(self, field: str, value: object):
        self._filters.append(("eq", field, value))
        return self

    def gte(self, field: str, value: object):
        self._filters.append(("gte", field, value))
        return self

    def lte(self, field: str, value: object):
        self._filters.append(("lte", field, value))
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    @staticmethod
    def _field_value(row: dict, field: str):
        value = row
        for part in field.split("."):
            if isinstance(value, list):
                value = value[0] if value else None
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def execute(self):
        if self.selected_columns and "profiles!inner(" in self.selected_columns:
            raise AssertionError("Search query must disambiguate the profiles relation")

        rows = [deepcopy(row) for row in self.rows]

        for operation, field, expected in self._filters:
            if operation == "ilike":
                needle = str(expected).replace("%", "").replace("*", "").lower()
                rows = [
                    row for row in rows
                    if needle in str(self._field_value(row, field) or "").lower()
                ]
            elif operation == "or":
                clauses = [clause.strip() for clause in str(expected).split(",") if clause.strip()]

                def matches_clause(row: dict, clause: str) -> bool:
                    column, operator, value = clause.split(".", 2)
                    lookup_field = f"{field}.{column}" if field else column
                    if operator == "ilike":
                        needle = value.replace("%", "").replace("*", "").lower()
                        return needle in str(self._field_value(row, lookup_field) or "").lower()
                    raise AssertionError(f"Unsupported OR operator in test double: {operator}")

                rows = [row for row in rows if any(matches_clause(row, clause) for clause in clauses)]
            elif operation == "eq":
                rows = [row for row in rows if self._field_value(row, field) == expected]
            elif operation == "gte":
                rows = [
                    row for row in rows
                    if (self._field_value(row, field) or 0) >= expected
                ]
            elif operation == "lte":
                rows = [
                    row for row in rows
                    if (self._field_value(row, field) or 0) <= expected
                ]

        total = len(rows)

        if self._order_field:
            rows.sort(
                key=lambda row: self._field_value(row, self._order_field) or 0,
                reverse=self._order_desc,
            )

        if self._range:
            start, end = self._range
            rows = rows[start:end + 1]

        return _FakeSearchResult(rows, total)


class _FakeSearchClient:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.last_query: _FakeSearchQuery | None = None

    def table(self, table_name: str):
        assert table_name == "fundi_profiles"
        self.last_query = _FakeSearchQuery(self.rows)
        return self.last_query


def _make_bearer_token(secret: str, user_id: str = "user-123") -> str:
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated"},
        secret,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_get_my_profile_returns_existing_profile(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _FakeAdminClient(
        initial_tables={
            "profiles": {
                "user-123": {
                    "id": "user-123",
                    "role": "client",
                    "full_name": "Jane Wanjiku",
                    "phone": "+254712345678",
                    "email": "jane@example.com",
                    "county": "Nairobi",
                    "area": "Westlands",
                    "preferred_language": "en",
                    "avatar_url": None,
                    "mpesa_number": "+254712345678",
                    "is_verified": True,
                    "is_suspended": False,
                    "created_at": "2026-04-22T10:00:00Z",
                    "updated_at": "2026-04-22T10:00:00Z",
                }
            }
        }
    )

    monkeypatch.setattr(
        deps_module,
        "settings",
        SimpleNamespace(supabase_jwt_secret=secret),
    )
    monkeypatch.setattr(profiles_module, "get_admin_client", lambda: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/profiles/me",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
        )

    assert response.status_code == 200
    assert response.json()["profile"]["full_name"] == "Jane Wanjiku"
    assert response.json()["profile"]["phone"] == "+254712345678"
    assert response.json()["fundi_profile"] is None


@pytest.mark.asyncio
async def test_get_my_profile_auto_creates_default_profile_when_missing(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _FakeAdminClient()
    fake_lookup = _FakeAuthLookupClient(
        user_id="user-123",
        email="new-user@example.com",
    )

    monkeypatch.setattr(
        deps_module,
        "settings",
        SimpleNamespace(supabase_jwt_secret=secret),
    )
    monkeypatch.setattr(profiles_module, "get_admin_client", lambda: fake_admin)
    monkeypatch.setattr(profiles_module, "get_anon_client", lambda: fake_lookup)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/profiles/me",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["id"] == "user-123"
    assert payload["profile"]["role"] == "client"
    assert payload["profile"]["full_name"] == "User"
    assert payload["profile"]["email"] == "new-user@example.com"
    assert re.fullmatch(r"\+2540\d{8}", payload["profile"]["phone"])
    assert fake_admin.tables["profiles"]["user-123"]["phone"] == payload["profile"]["phone"]


@pytest.mark.asyncio
async def test_get_my_profile_rejects_suspended_user(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _FakeAdminClient(
        initial_tables={
            "profiles": {
                "user-123": {
                    "id": "user-123",
                    "role": "client",
                    "full_name": "Jane Wanjiku",
                    "phone": "+254712345678",
                    "email": "jane@example.com",
                    "county": "Nairobi",
                    "area": "Westlands",
                    "preferred_language": "en",
                    "avatar_url": None,
                    "mpesa_number": "+254712345678",
                    "is_verified": True,
                    "is_suspended": True,
                    "created_at": "2026-04-22T10:00:00Z",
                    "updated_at": "2026-04-22T10:00:00Z",
                }
            }
        }
    )

    monkeypatch.setattr(
        deps_module,
        "settings",
        SimpleNamespace(supabase_jwt_secret=secret),
    )
    monkeypatch.setattr(profiles_module, "get_admin_client", lambda: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/profiles/me",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is suspended. Contact support."


@pytest.mark.asyncio
async def test_get_public_profile_returns_wrapped_worker_profile(monkeypatch) -> None:
    fake_anon = _FakeAdminClient(
        initial_tables={
            "profiles": {
                "worker-123": {
                    "id": "worker-123",
                    "role": "fundi",
                    "full_name": "Jane Fundi",
                    "county": "Nairobi",
                    "area": "Kilimani",
                    "preferred_language": "sw",
                    "is_verified": True,
                    "created_at": "2026-04-22T10:00:00Z",
                }
            },
            "fundi_profiles": {
                "worker-123": {
                    "trade": "plumber",
                    "bio": "Trusted local fundi",
                    "is_available": True,
                }
            },
        }
    )

    monkeypatch.setattr(profiles_module, "get_anon_client", lambda: fake_anon)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/profiles/worker-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["id"] == "worker-123"
    assert payload["profile"]["full_name"] == "Jane Fundi"
    assert payload["profile"]["preferred_language"] == "sw"
    assert payload["profile"]["created_at"] == "2026-04-22T10:00:00Z"
    assert payload["fundi_profile"]["trade"] == "plumber"
    assert payload["fundi_profile"]["bio"] == "Trusted local fundi"


@pytest.mark.asyncio
async def test_get_public_profile_returns_wrapped_client_profile(monkeypatch) -> None:
    fake_anon = _FakeAdminClient(
        initial_tables={
            "profiles": {
                "client-123": {
                    "id": "client-123",
                    "role": "client",
                    "full_name": "Joseph Client",
                    "county": "Nairobi",
                    "area": "Westlands",
                    "preferred_language": "en",
                    "is_verified": False,
                    "created_at": "2026-04-24T10:00:00Z",
                }
            }
        }
    )

    monkeypatch.setattr(profiles_module, "get_anon_client", lambda: fake_anon)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/profiles/client-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["id"] == "client-123"
    assert payload["profile"]["full_name"] == "Joseph Client"
    assert payload["profile"]["preferred_language"] == "en"
    assert payload["profile"]["created_at"] == "2026-04-24T10:00:00Z"
    assert payload["fundi_profile"] is None


@pytest.mark.asyncio
async def test_search_fundis_filters_sorts_and_paginates_embedded_profiles(monkeypatch) -> None:
    fake_anon = _FakeSearchClient(
        [
            {
                "id": "fundi-1",
                "trade": "plumber",
                "skills": ["Leak repair", "Install"],
                "rate_min": 1200,
                "rate_max": 1800,
                "rating_avg": 4.6,
                "jobs_completed": 8,
                "is_available": True,
                "kyc_status": "approved",
                "profiles": {
                    "full_name": "Alice Fundi",
                    "avatar_url": "https://example.com/a.png",
                    "county": "Nairobi",
                    "area": "Westlands",
                    "is_verified": False,
                },
            },
            {
                "id": "fundi-2",
                "trade": "plumber",
                "skills": ["Pipes", "Emergency callouts"],
                "rate_min": 1400,
                "rate_max": 2200,
                "rating_avg": 4.9,
                "jobs_completed": 14,
                "is_available": True,
                "kyc_status": "approved",
                "profiles": {
                    "full_name": "Brian Fundi",
                    "avatar_url": None,
                    "county": "Nairobi",
                    "area": "Kilimani",
                    "is_verified": True,
                },
            },
            {
                "id": "fundi-3",
                "trade": "plumber",
                "skills": ["Maintenance"],
                "rate_min": 900,
                "rate_max": 1400,
                "rating_avg": 4.8,
                "jobs_completed": 20,
                "is_available": True,
                "kyc_status": "approved",
                "profiles": {
                    "full_name": "Cheap Fundi",
                    "avatar_url": None,
                    "county": "Nairobi",
                    "area": "South B",
                    "is_verified": True,
                },
            },
            {
                "id": "fundi-4",
                "trade": "electrician",
                "skills": ["Wiring"],
                "rate_min": 1500,
                "rate_max": 2400,
                "rating_avg": 4.7,
                "jobs_completed": 11,
                "is_available": True,
                "kyc_status": "approved",
                "profiles": {
                    "full_name": "Eve Spark",
                    "avatar_url": None,
                    "county": "Nairobi",
                    "area": "Lavington",
                    "is_verified": True,
                },
            },
        ]
    )

    monkeypatch.setattr(profiles_module, "get_anon_client", lambda: fake_anon)

    first_page = await profiles_module.search_fundis(
        trade="plumber",
        location="nairobi",
        min_rate=1000,
        max_rate=1500,
        min_rating=4.5,
        verified_only=True,
        available_only=True,
        sort_by="jobs",
        limit=1,
        offset=0,
    )

    assert first_page["total"] == 2
    assert first_page["offset"] == 0
    assert first_page["limit"] == 1
    assert [item["id"] for item in first_page["results"]] == ["fundi-2"]
    assert first_page["results"][0]["trade_label"] == "Plumber"
    assert first_page["results"][0]["skills"] == ["Pipes", "Emergency callouts"]
    assert first_page["results"][0]["is_verified"] is True

    second_page = await profiles_module.search_fundis(
        trade="plumber",
        location="nairobi",
        min_rate=1000,
        max_rate=1500,
        min_rating=4.5,
        verified_only=True,
        available_only=True,
        sort_by="jobs",
        limit=1,
        offset=1,
    )

    assert second_page["total"] == 2
    assert [item["id"] for item in second_page["results"]] == ["fundi-1"]
    assert fake_anon.last_query is not None
    assert "profiles!id!inner(" in (fake_anon.last_query.selected_columns or "")
