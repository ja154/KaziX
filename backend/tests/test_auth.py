from types import SimpleNamespace

import httpx
import pytest
from gotrue.errors import AuthApiError
from jose import jwt
from postgrest.exceptions import APIError

from app.api import deps as deps_module
from app.api.v1 import auth as auth_module
from app.main import app
from app.services import otp as otp_service_module


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


class _FakePasswordAuthClient:
    def __init__(
        self,
        *,
        user_id: str = "email-user-123",
        access_token: str = "email-access-token",
        refresh_token: str = "email-refresh-token",
        expires_in: int = 3600,
        sign_in_error: Exception | None = None,
    ) -> None:
        self.user_id = user_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.sign_in_error = sign_in_error
        self.payloads: list[dict] = []

    def sign_in_with_password(self, payload: dict):
        self.payloads.append(payload)
        if self.sign_in_error:
            raise self.sign_in_error
        return SimpleNamespace(
            user=SimpleNamespace(id=self.user_id),
            session=SimpleNamespace(
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                expires_in=self.expires_in,
            ),
        )


class _FakePasswordClient:
    def __init__(self, auth_client: _FakePasswordAuthClient) -> None:
        self.auth = auth_client


class _FakeAdminUserAdmin:
    def __init__(
        self,
        *,
        user_id: str = "email-user-123",
        create_error: Exception | None = None,
    ) -> None:
        self.user_id = user_id
        self.create_error = create_error
        self.payloads: list[dict] = []

    def create_user(self, payload: dict):
        self.payloads.append(payload)
        if self.create_error:
            raise self.create_error
        return SimpleNamespace(user=SimpleNamespace(id=self.user_id))


class _FakeRegisterAdminClient:
    def __init__(self, user_admin: _FakeAdminUserAdmin) -> None:
        self.auth = SimpleNamespace(admin=user_admin)


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
async def test_email_register_creates_confirmed_user_and_signs_in(monkeypatch) -> None:
    fake_user_admin = _FakeAdminUserAdmin(user_id="new-email-user")
    fake_admin = _FakeRegisterAdminClient(fake_user_admin)
    fake_password_auth = _FakePasswordAuthClient(user_id="new-email-user")
    fake_password_client = _FakePasswordClient(fake_password_auth)

    monkeypatch.setattr(auth_module, "get_admin_client", lambda: fake_admin)
    monkeypatch.setattr(auth_module, "create_client", lambda *_args, **_kwargs: fake_password_client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/email/register",
            json={
                "email": "jane@example.com",
                "password": "SecurePass123!",
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "access_token": "email-access-token",
        "refresh_token": "email-refresh-token",
        "token_type": "bearer",
        "expires_in": 3600,
        "is_new_user": True,
        "redirect_to": "complete-registration",
    }
    assert fake_user_admin.payloads == [
        {
            "email": "jane@example.com",
            "password": "SecurePass123!",
            "email_confirm": True,
        }
    ]
    assert fake_password_auth.payloads == [
        {
            "email": "jane@example.com",
            "password": "SecurePass123!",
        }
    ]


@pytest.mark.asyncio
async def test_email_register_returns_conflict_for_duplicate_email(monkeypatch) -> None:
    fake_user_admin = _FakeAdminUserAdmin(
        create_error=AuthApiError("User already registered", 422, "user_already_exists")
    )
    fake_admin = _FakeRegisterAdminClient(fake_user_admin)

    monkeypatch.setattr(auth_module, "get_admin_client", lambda: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/email/register",
            json={
                "email": "jane@example.com",
                "password": "SecurePass123!",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "An account with that email already exists. Sign in instead."


@pytest.mark.asyncio
async def test_email_login_returns_existing_profile_redirect(monkeypatch) -> None:
    fake_password_auth = _FakePasswordAuthClient(user_id="existing-email-user")
    fake_password_client = _FakePasswordClient(fake_password_auth)
    fake_admin = _FakeAdminClient(
        initial_tables={
            "profiles": {
                "existing-email-user": {
                    "id": "existing-email-user",
                    "role": "fundi",
                    "full_name": "Jane Fundi",
                    "phone": "+254712345678",
                    "is_verified": True,
                }
            }
        }
    )

    monkeypatch.setattr(auth_module, "create_client", lambda *_args, **_kwargs: fake_password_client)
    monkeypatch.setattr(auth_module, "get_admin_client", lambda: fake_admin)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/email/login",
            json={
                "email": "jane@example.com",
                "password": "SecurePass123!",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "email-access-token",
        "refresh_token": "email-refresh-token",
        "token_type": "bearer",
        "expires_in": 3600,
        "is_new_user": False,
        "redirect_to": "fundi-dashboard",
    }


@pytest.mark.asyncio
async def test_email_login_returns_unauthorized_for_bad_credentials(monkeypatch) -> None:
    fake_password_auth = _FakePasswordAuthClient(
        sign_in_error=AuthApiError("Invalid login credentials", 400, "invalid_credentials")
    )
    fake_password_client = _FakePasswordClient(fake_password_auth)

    monkeypatch.setattr(auth_module, "create_client", lambda *_args, **_kwargs: fake_password_client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/email/login",
            json={
                "email": "jane@example.com",
                "password": "SecurePass123!",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


@pytest.mark.asyncio
async def test_send_otp_for_signup_forwards_magic_link_redirect(monkeypatch) -> None:
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(otp_service_module, "get_anon_client", lambda: fake_client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/send-otp",
            json={
                "email": "test@example.com",
                "email_redirect_to": "http://localhost:5000/pages/auth-callback.html",
                "should_create_user": True,
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
async def test_send_otp_for_login_keeps_magic_link_login_only(monkeypatch) -> None:
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(otp_service_module, "get_anon_client", lambda: fake_client)

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
    assert fake_client.auth.payloads == [
        {
            "email": "test@example.com",
            "options": {
                "should_create_user": False,
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
async def test_create_profile_falls_back_to_admin_client_when_user_upsert_fails(monkeypatch) -> None:
    secret = "test-jwt-secret"
    failing_user_client = _ErroringAdminClient(
        execute_errors={
            "profiles": {
                "message": 'new row violates row-level security policy for table "profiles"',
                "code": "42501",
                "details": "",
                "hint": "",
            }
        }
    )
    fake_admin = _FakeAdminClient()

    monkeypatch.setattr(deps_module, "settings", SimpleNamespace(supabase_jwt_secret=secret))
    monkeypatch.setattr(auth_module, "get_user_client", lambda _token: failing_user_client)
    monkeypatch.setattr(auth_module, "get_admin_client", lambda: fake_admin)

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
