import re
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
