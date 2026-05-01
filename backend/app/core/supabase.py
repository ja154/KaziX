"""
app/core/supabase.py
────────────────────
Supabase client factories:

  get_anon_client()     → uses ANON key. Safe for public/user-scoped reads.
  get_admin_client()    → uses SERVICE ROLE key. Server-side only.
  get_user_client()     → request-scoped client authenticated as a user.

These clients are intentionally created per call. Supabase auth/session state is
mutable, so caching a shared client can leak headers between requests and cause
unexpected RLS failures.
"""

import httpx

from app.core.config import get_settings
from supabase import Client, ClientOptions, create_client

# Generous timeouts so that Supabase email/SMS OTP sends never time out
# on slow cold-start or under DNS/network variability.
_TIMEOUT = httpx.Timeout(
    connect=10.0,   # TCP handshake
    read=30.0,      # wait for Supabase to finish sending the OTP
    write=10.0,
    pool=5.0,
)

_CLIENT_OPTIONS = ClientOptions(
    postgrest_client_timeout=_TIMEOUT,
    storage_client_timeout=_TIMEOUT,
    function_client_timeout=_TIMEOUT,
)


def _patch_auth_timeout(client: Client) -> Client:
    """
    The GoTrue auth client (used for OTP send/verify) has a separate
    HTTP client with a hardcoded 5-second timeout.  Patch it to match
    our generous timeout so email OTP sends don't time out.
    """
    auth_http = getattr(client.auth, "_http_client", None)
    if auth_http is not None:
        auth_http.timeout = _TIMEOUT
    return client


def get_anon_client() -> Client:
    """
    Public Supabase client — respects RLS policies.
    Use for all user-facing data operations.
    """
    s = get_settings()
    client = create_client(s.supabase_url, s.supabase_anon_key, options=_CLIENT_OPTIONS)
    return _patch_auth_timeout(client)
 
 
def get_admin_client() -> Client:
    """
    Admin Supabase client — bypasses RLS (service role key).
    Strictly server-side only:
      - OTP verification flows
      - Background jobs
      - Admin API routes
      - Webhook handlers
    """
    s = get_settings()
    client = create_client(s.supabase_url, s.supabase_service_role_key, options=_CLIENT_OPTIONS)
    return _patch_auth_timeout(client)


def get_user_client(access_token: str) -> Client:
    """
    Request-scoped Supabase client that executes PostgREST calls as the
    authenticated user. This keeps user-owned writes aligned with RLS.
    """
    s = get_settings()
    client = create_client(s.supabase_url, s.supabase_anon_key, options=_CLIENT_OPTIONS)
    client.postgrest.auth(access_token)
    return _patch_auth_timeout(client)
