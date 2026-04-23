import pytest
from gotrue.errors import AuthApiError
from fastapi import status
from app.api.v1.auth import _auth_error_http_exception
from unittest.mock import MagicMock

def test_auth_error_http_exception_mapping():
    # Test rate limit
    exc = AuthApiError("Rate limit exceeded", 429, "over_request_rate_limit")
    http_exc = _auth_error_http_exception(exc, default_status=400, default_detail="Error")
    assert http_exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Too many requests" in http_exc.detail

    # Test signup disabled
    exc = AuthApiError("Signups are not allowed", 403, "signup_disabled")
    http_exc = _auth_error_http_exception(exc, default_status=400, default_detail="Error")
    assert http_exc.status_code == status.HTTP_403_FORBIDDEN
    assert "Signups are currently disabled" in http_exc.detail

    # Test weak password (using code)
    exc = AuthApiError("Password is too short", 422, "weak_password")
    http_exc = _auth_error_http_exception(exc, default_status=400, default_detail="Error")
    assert http_exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "too short" in http_exc.detail.lower() or "too weak" in http_exc.detail.lower()

    # Test invalid email (using blob)
    exc = AuthApiError("Email address is invalid", 422, None)
    http_exc = _auth_error_http_exception(exc, default_status=400, default_detail="Error")
    assert http_exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "email address provided is invalid" in http_exc.detail.lower()

    # Test generic error in production
    # We need to mock settings to be in production
    from app.api.v1 import auth
    original_settings = auth.settings
    auth.settings = MagicMock()
    auth.settings.app_env = "production"

    try:
        exc = AuthApiError("Internal Supabase Error", 500, "unknown_code")
        http_exc = _auth_error_http_exception(exc, default_status=500, default_detail="Generic Production Error")
        assert http_exc.status_code == 500
        assert http_exc.detail == "Generic Production Error"
    finally:
        # Restore settings
        auth.settings = original_settings
