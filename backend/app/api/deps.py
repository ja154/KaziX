"""
app/api/deps.py
───────────────
FastAPI dependency functions.
Import these with Depends() in route handlers.
"""

from functools import lru_cache
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError, AuthRetryableError
from jose import JWTError, jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.supabase import get_admin_client

logger = get_logger(__name__)
settings = get_settings()

_bearer = HTTPBearer(auto_error=True)


class AuthenticatedUser:
    """Carries the decoded JWT payload + resolved profile row."""

    def __init__(self, user_id: str, role: str, phone: str):
        self.user_id = user_id
        self.role = role
        self.phone = phone


class AuthenticatedSession:
    """Carries the decoded JWT payload for any authenticated Supabase session."""

    def __init__(self, user_id: str, access_token: str):
        self.user_id = user_id
        self.access_token = access_token


@lru_cache(maxsize=4)
def _get_supabase_jwk_client(supabase_url: str) -> PyJWKClient:
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(
        jwks_url,
        cache_jwk_set=True,
        lifespan=300,
        timeout=5,
    )


def _decode_asymmetric_user_id(token: str) -> str:
    signing_key = _get_supabase_jwk_client(settings.supabase_url).get_signing_key_from_jwt(token)
    payload = pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )
    user_id = payload.get("sub")
    if not user_id:
        raise JWTError("Missing user id in authenticated session")
    return str(user_id)


def _decode_user_id(credentials: HTTPAuthorizationCredentials) -> str:
    """Validate the bearer token and return the authenticated user id."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials

    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        header = {}

    alg = str(header.get("alg") or "").upper()

    try:
        # Supabase can issue either symmetric or asymmetric access tokens.
        # Keep local HS256 verification for simple/test setups and fall back
        # to the Auth API for newer asymmetric tokens.
        if alg in {"", "HS256"}:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
            user_id: str = payload.get("sub")
        else:
            user_id = _decode_asymmetric_user_id(token)

        if not user_id:
            raise JWTError("Missing user id in authenticated session")

        return user_id
    except (AuthApiError, AuthRetryableError, InvalidTokenError, PyJWKClientError, JWTError) as exc:
        logger.warning("JWT validation failed", alg=alg or None, error=str(exc))
        raise credentials_exception


async def get_authenticated_session(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> AuthenticatedSession:
    """
    Validates the Supabase-issued JWT from the Authorization header.
    Returns the authenticated user id even before a profile exists.
    """
    return AuthenticatedSession(
        user_id=_decode_user_id(credentials),
        access_token=credentials.credentials,
    )


async def get_current_user(
    session: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
) -> AuthenticatedUser:
    """
    Resolves a full profile-backed AuthenticatedUser for routes that require one.

    Raises 401 on missing/invalid token or missing profile, 403 if suspended.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Fetch the profile to get role and suspension status
    client = get_admin_client()
    try:
        result = (
            client.table("profiles")
            .select("id, role, phone, is_suspended")
            .eq("id", session.user_id)
            .single()
            .execute()
        )

        if not result.data:
            raise credentials_exception

        profile = result.data
        if profile.get("is_suspended"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is suspended. Contact support.",
            )

        return AuthenticatedUser(
            user_id=profile["id"],
            role=profile["role"],
            phone=profile["phone"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Database error in get_current_user", error=str(e))
        raise credentials_exception


def require_role(*roles: str):
    """
    Factory: returns a dependency that enforces one of the given roles.

    Usage:
        @router.get("/admin/users")
        async def list_users(
            _: Annotated[AuthenticatedUser, Depends(require_role("admin"))]
        ): ...
    """

    async def _check(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(roles)}",
            )
        return user

    return _check


# Convenience aliases
CurrentSession = Annotated[AuthenticatedSession, Depends(get_authenticated_session)]
CurrentUser    = Annotated[AuthenticatedUser, Depends(get_current_user)]
AdminUser      = Annotated[AuthenticatedUser, Depends(require_role("admin"))]
FundiUser      = Annotated[AuthenticatedUser, Depends(require_role("fundi", "admin"))]
ClientUser     = Annotated[AuthenticatedUser, Depends(require_role("client", "admin"))]
