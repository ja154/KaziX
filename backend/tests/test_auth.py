from types import SimpleNamespace

import httpx
import pytest
from jose import jwt
from postgrest.exceptions import APIError

from app.api import deps as deps_module
from app.api.v1 import auth as auth_module
from app.main import app


class _FakeAuthClient:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def sign_in_with_otp(self, payload: dict):
        self.payloads.append(payload)
        return {"ok": True}


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.auth = _FakeAuthClient()


class _FakeAuthLookupClient:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.auth = SimpleNamespace(
            get_user=lambda jwt=None: SimpleNamespace(
                user=SimpleNamespace(id=self.user_id)
            )
        )


class _FakeLogoutAdmin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def sign_out(self, jwt: str, scope: str = "global") -> None:
        self.calls.append((jwt, scope))


class _FakeLogoutClient:
    def __init__(self) -> None:
        self.auth = SimpleNamespace(admin=_FakeLogoutAdmin())


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

    def upsert(self, payload: dict, on_conflict: str | None = None):
        del on_conflict
        self._operation = "upsert"
        self._payload = dict(payload)
        return self

    def execute(self):
        table = self.tables.setdefault(self.table_name, {})
        if self._operation == "upsert":
            row = dict(self._payload)
            table[row["id"]] = row
            return _FakeResult([row])

        if self._operation == "select":
            row = table.get(self._filters.get("id"))
            return _FakeResult(dict(row) if row else None)

        raise AssertionError(f"Unexpected operation: {self._operation}")


class _FakeAdminClient:
    def __init__(self, initial_tables: dict[str, dict[str, dict]] | None = None) -> None:
        self.tables = initial_tables or {}

    def table(self, table_name: str):
        return _FakeTableQuery(self.tables, table_name)


class _ErroringTableQuery(_FakeTableQuery):
    def __init__(
        self,
        tables: dict[str, dict[str, dict]],
        table_name: str,
        execute_error: dict[str, str] | None = None,
    ) -> None:
        super().__init__(tables, table_name)
        self._execute_error = execute_error

    def execute(self):
        if self._operation == "upsert" and self._execute_error:
            raise APIError(self._execute_error)
        return super().execute()


class _ErroringAdminClient(_FakeAdminClient):
    def __init__(
        self,
        execute_errors: dict[str, dict[str, str]],
        initial_tables: dict[str, dict[str, dict]] | None = None,
    ) -> None:
        super().__init__(initial_tables=initial_tables)
        self.execute_errors = execute_errors

    def table(self, table_name: str):
        return _ErroringTableQuery(
            self.tables,
            table_name,
            execute_error=self.execute_errors.get(table_name),
        )


def _make_bearer_token(secret: str, user_id: str = "user-123") -> str:
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated"},
        secret,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_send_otp_for_signup_forwards_magic_link_redirect(monkeypatch) -> None:
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(auth_module, "get_anon_client", lambda: fake_client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/send-otp",
            json={
                "email": "test@example.com",
                "email_redirect_to": "http://localhost:5000/pages/auth-callback.html",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Magic link sent successfully",
    }
    assert fake_client.auth.payloads == [
        {
            "email": "test@example.com",
            "options": {
                "should_create_user": True,
                "email_redirect_to": "http://localhost:5000/pages/auth-callback.html",
            },
        }
    ]


@pytest.mark.asyncio
async def test_send_otp_rejects_redirect_for_phone_destination() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/send-otp",
            json={
                "phone": "+254712345678",
                "email_redirect_to": "http://localhost:5000/pages/auth-callback.html",
            },
        )

    assert response.status_code == 422
    assert "email_redirect_to" in response.text


@pytest.mark.asyncio
async def test_create_profile_allows_authenticated_new_user_without_existing_profile(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _FakeAdminClient()
    monkeypatch.setattr(deps_module, "settings", SimpleNamespace(supabase_jwt_secret=secret))
    monkeypatch.setattr(auth_module, "get_user_client", lambda _token: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/profile",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
            json={
                "full_name": "Jane Wanjiku",
                "phone": "+254712345678",
                "email": "jane@example.com",
                "county": "Nairobi",
                "area": "Westlands",
                "role": "client",
                "mpesa_number": "+254712345678",
                "preferred_language": "en",
            },
        )

    assert response.status_code == 201
    assert response.json()["success"] is True
    assert fake_admin.tables["profiles"]["user-123"]["full_name"] == "Jane Wanjiku"
    assert fake_admin.tables["profiles"]["user-123"]["role"] == "client"


@pytest.mark.asyncio
async def test_create_profile_returns_conflict_for_duplicate_phone(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _ErroringAdminClient(
        execute_errors={
            "profiles": {
                "message": 'duplicate key value violates unique constraint "uq_profiles_phone"',
                "code": "23505",
                "details": "Key (phone)=(+254712345678) already exists.",
                "hint": "",
            }
        }
    )
    monkeypatch.setattr(deps_module, "settings", SimpleNamespace(supabase_jwt_secret=secret))
    monkeypatch.setattr(auth_module, "get_user_client", lambda _token: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/profile",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
            json={
                "full_name": "Jane Wanjiku",
                "phone": "+254712345678",
                "email": "jane@example.com",
                "county": "Nairobi",
                "area": "Westlands",
                "role": "client",
                "mpesa_number": "+254712345678",
                "preferred_language": "en",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "That phone number is already linked to another account. "
        "Sign in instead or use a different number."
    )


@pytest.mark.asyncio
async def test_create_profile_rejects_inverted_fundi_rate_range(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _FakeAdminClient()
    monkeypatch.setattr(deps_module, "settings", SimpleNamespace(supabase_jwt_secret=secret))
    monkeypatch.setattr(auth_module, "get_user_client", lambda _token: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/profile",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
            json={
                "full_name": "Jane Wanjiku",
                "phone": "+254712345678",
                "email": "jane@example.com",
                "county": "Nairobi",
                "area": "Westlands",
                "role": "fundi",
                "trade": "plumber",
                "rate_min": 2000,
                "rate_max": 800,
                "experience_years": 5,
                "bio": "Experienced plumber",
                "mpesa_number": "+254712345678",
                "preferred_language": "en",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Maximum rate must be greater than or equal to minimum rate."
    assert fake_admin.tables == {}


@pytest.mark.asyncio
async def test_bootstrap_allows_authenticated_new_user_without_existing_profile(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_admin = _FakeAdminClient()
    monkeypatch.setattr(deps_module, "settings", SimpleNamespace(supabase_jwt_secret=secret))
    monkeypatch.setattr(auth_module, "get_admin_client", lambda: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/auth/bootstrap",
            headers={"Authorization": f"Bearer {_make_bearer_token(secret)}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "is_new_user": True,
        "redirect_to": "complete-registration",
        "role": "client",
        "profile": None,
    }


@pytest.mark.asyncio
async def test_bootstrap_accepts_asymmetric_supabase_tokens(monkeypatch) -> None:
    fake_admin = _FakeAdminClient()
    fake_lookup_client = _FakeAuthLookupClient(user_id="user-rs256")

    monkeypatch.setattr(
        deps_module,
        "settings",
        SimpleNamespace(supabase_jwt_secret="test-jwt-secret"),
    )
    monkeypatch.setattr(deps_module, "get_anon_client", lambda: fake_lookup_client)
    monkeypatch.setattr(
        deps_module.jwt,
        "get_unverified_header",
        lambda _token: {"alg": "RS256"},
    )
    monkeypatch.setattr(auth_module, "get_admin_client", lambda: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/auth/bootstrap",
            headers={"Authorization": "Bearer asymmetric-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "is_new_user": True,
        "redirect_to": "complete-registration",
        "role": "client",
        "profile": None,
    }


@pytest.mark.asyncio
async def test_logout_uses_authenticated_session_token(monkeypatch) -> None:
    secret = "test-jwt-secret"
    fake_client = _FakeLogoutClient()
    access_token = _make_bearer_token(secret)

    monkeypatch.setattr(
        deps_module,
        "settings",
        SimpleNamespace(supabase_jwt_secret=secret),
    )
    monkeypatch.setattr(auth_module, "get_anon_client", lambda: fake_client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Logged out successfully",
    }
    assert fake_client.auth.admin.calls == [(access_token, "global")]
