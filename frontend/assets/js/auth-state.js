(function () {
  const DEFAULT_REMOTE_API_BASE = 'https://kazix.onrender.com';
  const SAME_ORIGIN_PROXY_HOSTS = new Set([
    'kazixfrontend.vercel.app',
    'kazix.vercel.app',
    'kazix.co.ke',
    'www.kazix.co.ke',
  ]);
  const PROFILE_CACHE_KEY = 'kazix_profile';
  const TOKEN_KEYS = ['kazix_access_token', 'sb-access-token', 'access_token'];
  const AUTH_STORAGE_KEYS = new Set([
    'kazix_access_token',
    'kazix_refresh_token',
    'kazix_expires_in',
    'kazix_expires_at',
    'kazix_token_type',
    'kazix_user_id',
    'kazix_role',
    'kazix_login_email',
    'kazix_magic_link_complete',
    'kazix_auth_next_page',
    'kazix_auth_flow',
    'kazix_auth_waiter_id',
    'kazix_auth_waiting_owner',
    'kazix_auth_waiting_flow',
    'kazix_auth_waiting_heartbeat',
    'kazix_auth_waiting_started_at',
    'kazix_reg_pending_profile',
    PROFILE_CACHE_KEY,
  ]);
  const AUTH_STORAGE_PREFIXES = ['kazix_reg_'];
  const AUTH_REFRESH_BUFFER_MS = 60 * 1000;
  let refreshSessionPromise = null;

  function normalizeApiBase(candidate) {
    if (candidate === undefined || candidate === null) {
      return null;
    }

    const value = String(candidate).trim();
    if (!value) {
      return null;
    }

    try {
      const url = new URL(value, window.location.origin);
      if (url.origin === window.location.origin && url.pathname === '/') {
        return '';
      }
      return url.toString().replace(/\/$/, '');
    } catch (_error) {
      return value.replace(/\/$/, '');
    }
  }

  function isLocalHost(host) {
    return ['localhost', '127.0.0.1', '0.0.0.0'].includes(host);
  }

  function shouldUseSameOriginProxy(host) {
    return SAME_ORIGIN_PROXY_HOSTS.has(host) || host.endsWith('.vercel.app') || host.endsWith('.kazix.co.ke');
  }

  function resolveApiBase() {
    const configured = normalizeApiBase(window.KAZIX_API_BASE ?? window.KAZIX_CONFIG?.KAZIX_API_BASE ?? null);
    if (configured !== null) {
      return configured;
    }

    if (window.KazixProfile?.API_BASE) {
      return window.KazixProfile.API_BASE;
    }

    if (isLocalHost(window.location.hostname)) {
      return window.location.origin.replace(/\/$/, '');
    }

    if (shouldUseSameOriginProxy(window.location.hostname)) {
      return '';
    }

    return DEFAULT_REMOTE_API_BASE;
  }

  const API_BASE = resolveApiBase();

  function isSupabaseStorageKey(key) {
    return key === 'supabase.auth.token'
      || /^sb-[a-z0-9_-]+-auth-token(?:-code-verifier)?$/i.test(key);
  }

  function safeJson(text) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  }

  function looksLikeToken(value) {
    return typeof value === 'string'
      && value.trim().length > 20
      && (value.includes('.') || /^[A-Za-z0-9_-]+$/.test(value.trim()));
  }

  function extractToken(payload) {
    if (!payload) return null;

    if (typeof payload === 'string') {
      const value = payload.trim();
      return looksLikeToken(value) ? value : null;
    }

    if (Array.isArray(payload)) {
      for (const item of payload) {
        const token = extractToken(item);
        if (token) return token;
      }
      return null;
    }

    if (typeof payload === 'object') {
      if (typeof payload.access_token === 'string') {
        return payload.access_token.trim();
      }

      return extractToken(payload.currentSession) || extractToken(payload.session);
    }

    return null;
  }

  function parseStoredToken(value) {
    if (!value) return null;
    const text = String(value).trim();
    if (!text) return null;
    return extractToken(safeJson(text)) || extractToken(text);
  }

  function findTokenInStorage(storage) {
    if (!storage) return null;

    for (const key of TOKEN_KEYS) {
      const token = parseStoredToken(storage.getItem(key));
      if (token) return token;
    }

    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (!key || !isSupabaseStorageKey(key)) continue;
      const token = parseStoredToken(storage.getItem(key));
      if (token) return token;
    }

    return null;
  }

  function getToken() {
    return findTokenInStorage(window.localStorage) || findTokenInStorage(window.sessionStorage);
  }

  function getRefreshToken() {
    return window.localStorage.getItem('kazix_refresh_token');
  }

  function getStoredExpiresAtSeconds() {
    const value = Number(window.localStorage.getItem('kazix_expires_at'));
    if (!Number.isFinite(value) || value <= 0) {
      return null;
    }

    return Math.floor(value > 1e12 ? value / 1000 : value);
  }

  function getStoredExpiresAtMs() {
    const expiresAtSeconds = getStoredExpiresAtSeconds();
    return expiresAtSeconds ? expiresAtSeconds * 1000 : null;
  }

  function computeExpiresAtSeconds(payload) {
    const rawExpiresAt = Number(payload?.expires_at);
    if (Number.isFinite(rawExpiresAt) && rawExpiresAt > 0) {
      return Math.floor(rawExpiresAt > 1e12 ? rawExpiresAt / 1000 : rawExpiresAt);
    }

    const expiresIn = Number(payload?.expires_in);
    if (Number.isFinite(expiresIn) && expiresIn > 0) {
      return Math.floor(Date.now() / 1000) + Math.floor(expiresIn);
    }

    return null;
  }

  function persistSession(payload) {
    if (!payload?.access_token) return null;

    const expiresIn = Number(payload.expires_in);
    const expiresAt = computeExpiresAtSeconds(payload);

    window.localStorage.setItem('kazix_access_token', payload.access_token);
    if (payload.refresh_token) {
      window.localStorage.setItem('kazix_refresh_token', payload.refresh_token);
    }
    if (Number.isFinite(expiresIn) && expiresIn > 0) {
      window.localStorage.setItem('kazix_expires_in', String(Math.floor(expiresIn)));
    } else {
      window.localStorage.removeItem('kazix_expires_in');
    }
    if (expiresAt !== null) {
      window.localStorage.setItem('kazix_expires_at', String(expiresAt));
    } else {
      window.localStorage.removeItem('kazix_expires_at');
    }
    window.localStorage.setItem(
      'kazix_token_type',
      payload.token_type || window.localStorage.getItem('kazix_token_type') || 'bearer'
    );

    return payload.access_token;
  }

  function shouldRefreshAccessToken() {
    const expiresAtMs = getStoredExpiresAtMs();
    return Boolean(
      getToken()
      && getRefreshToken()
      && expiresAtMs
      && expiresAtMs <= (Date.now() + AUTH_REFRESH_BUFFER_MS)
    );
  }

  async function refreshAccessToken(options = {}) {
    if (window.KazixProfile && typeof window.KazixProfile.refreshAccessToken === 'function') {
      return window.KazixProfile.refreshAccessToken(options);
    }

    const { force = false } = options;
    const currentToken = getToken();
    const refreshToken = getRefreshToken();

    if (!refreshToken) {
      return force ? null : currentToken;
    }

    if (!force && !shouldRefreshAccessToken()) {
      return currentToken;
    }

    if (refreshSessionPromise) {
      return refreshSessionPromise;
    }

    refreshSessionPromise = (async () => {
      const res = await fetch(`${API_BASE}/v1/auth/oauth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      const text = await res.text();
      const data = text ? safeJson(text) : {};

      if (!res.ok || !data?.access_token) {
        const error = new Error(
          data?.detail || text || `Could not refresh session (${res.status})`
        );
        error.status = res.status;
        if (res.status === 400 || res.status === 401) {
          clearAuth();
        }
        throw error;
      }

      return persistSession(data);
    })().finally(() => {
      refreshSessionPromise = null;
    });

    return refreshSessionPromise;
  }

  async function getValidAccessToken(options = {}) {
    if (window.KazixProfile && typeof window.KazixProfile.getValidAccessToken === 'function') {
      return window.KazixProfile.getValidAccessToken(options);
    }

    const { forceRefresh = false } = options;
    const currentToken = getToken();
    if (!currentToken) return null;

    const shouldRefresh = forceRefresh || shouldRefreshAccessToken();
    if (!shouldRefresh) {
      return currentToken;
    }

    try {
      return await refreshAccessToken({ force: true });
    } catch (error) {
      if (forceRefresh || error?.status === 400 || error?.status === 401) {
        return null;
      }
      return getToken() || currentToken;
    }
  }

  function normalizeProfile(data) {
    const profile = data?.profile || data || null;
    if (!profile || typeof profile !== 'object') return null;
    if (!profile.id && !profile.email && !profile.full_name && !profile.name) return null;
    return profile;
  }

  function getCachedProfile() {
    return normalizeProfile(safeJson(window.localStorage.getItem(PROFILE_CACHE_KEY) || 'null'));
  }

  function isPendingRegistration() {
    return window.localStorage.getItem('kazix_reg_pending_profile') === '1'
      || window.localStorage.getItem('kazix_auth_flow') === 'register';
  }

  function clearMatchingStorage(storage) {
    if (!storage) return;

    for (let index = storage.length - 1; index >= 0; index -= 1) {
      const key = storage.key(index);
      if (!key) continue;
      if (
        AUTH_STORAGE_KEYS.has(key)
        || AUTH_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix))
        || isSupabaseStorageKey(key)
      ) {
        storage.removeItem(key);
      }
    }
  }

  function clearAuth() {
    refreshSessionPromise = null;
    clearMatchingStorage(window.localStorage);
    clearMatchingStorage(window.sessionStorage);
    delete window.KaziXUser;
  }

  async function fetchProfile(token, options = {}) {
    const { retried = false } = options;

    try {
      const res = await fetch(`${API_BASE}/v1/profiles/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
        if (!retried) {
          const refreshedToken = await getValidAccessToken({ forceRefresh: true });
          if (refreshedToken) {
            return fetchProfile(refreshedToken, { retried: true });
          }
        }
        clearAuth();
        return null;
      }

      if (res.status === 404) {
        if (!isPendingRegistration()) {
          clearAuth();
        }
        return null;
      }

      if (!res.ok) {
        return null;
      }

      return normalizeProfile(await res.json());
    } catch (_error) {
      return null;
    }
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function initials(profile) {
    const name = profile.full_name || profile.name || profile.email || profile.phone || 'U';
    return String(name)
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((part) => part[0])
      .slice(0, 2)
      .join('')
      .toUpperCase() || 'U';
  }

  function profileHref(profile) {
    const role = String(profile.role || '').toLowerCase();
    if (role === 'worker' || role === 'fundi') return 'worker-profile-edit.html';
    if (role === 'admin') return 'admin-dashboard.html';
    return 'client-profile.html';
  }

  function renderSignedIn(profile) {
    document
      .querySelectorAll('[data-auth="guest"]')
      .forEach((el) => {
        el.style.display = 'none';
      });

    document
      .querySelectorAll('[data-auth="user"]')
      .forEach((el) => {
        el.style.display = '';
      });

    document.querySelectorAll('[data-auth-slot="profile"]').forEach((slot) => {
      slot.style.display = '';
      slot.innerHTML = `
        <div class="auth-chip" style="display:inline-flex;align-items:center;gap:.6rem;flex-wrap:wrap;">
          <a href="${profileHref(profile)}"
             style="display:inline-flex;align-items:center;gap:.5rem;text-decoration:none;color:inherit;">
            <span style="width:36px;height:36px;border-radius:50%;background:#F5A623;color:#0D0D0D;display:inline-flex;align-items:center;justify-content:center;font-weight:700;">
              ${escapeHtml(initials(profile))}
            </span>
            <span class="auth-chip__name" style="font-weight:600;">
              ${escapeHtml(profile.full_name || profile.email || 'Account')}
            </span>
          </a>
          <button type="button"
                  data-auth-action="logout"
                  style="background:none;border:1px solid #0D0D0D;border-radius:999px;padding:.4rem .8rem;cursor:pointer;font:inherit;">
            Log out
          </button>
        </div>
      `;
    });
  }

  function renderGuest() {
    document
      .querySelectorAll('[data-auth="guest"]')
      .forEach((el) => {
        el.style.display = '';
      });

    document
      .querySelectorAll('[data-auth="user"]')
      .forEach((el) => {
        el.style.display = 'none';
      });

    document.querySelectorAll('[data-auth-slot="profile"]').forEach((slot) => {
      slot.style.display = 'none';
      slot.innerHTML = '';
    });
  }

  async function logout() {
    if (window.KazixProfile && typeof window.KazixProfile.logout === 'function') {
      // Delegate to the canonical implementation in profile-utils.js
      // so we have one source of truth for clearing storage + redirect.
      return window.KazixProfile.logout();
    }
    // Fallback used only when profile-utils.js is not present on the page.
    const token = getToken();
    try {
      if (token) {
        await fetch(`${API_BASE}/v1/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch (_error) {
      // Ignore API logout failures and clear local state anyway.
    } finally {
      clearAuth();
      window.location.replace('login.html?logged_out=1');
    }
  }

  async function init() {
    renderGuest();

    const token = await getValidAccessToken();
    if (!token) return;

    const cachedProfile = getCachedProfile();
    if (cachedProfile) {
      window.KaziXUser = cachedProfile;
      renderSignedIn(cachedProfile);
    }

    const profile = await fetchProfile(token);
    if (!profile) {
      if (!getToken() || !cachedProfile) {
        renderGuest();
      }
      return;
    }

    window.localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(profile));
    if (profile.role) {
      window.localStorage.setItem('kazix_role', profile.role);
    }
    window.KaziXUser = profile;
    renderSignedIn(profile);
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-auth-action="logout"]');
    if (!button) return;
    event.preventDefault();
    logout();
  });

  window.addEventListener('storage', (event) => {
    if (
      !event.key
      || TOKEN_KEYS.includes(event.key)
      || AUTH_STORAGE_KEYS.has(event.key)
      || isSupabaseStorageKey(event.key)
    ) {
      init();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
