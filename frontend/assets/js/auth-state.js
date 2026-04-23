(function () {
  const DEFAULT_REMOTE_API_BASE = 'https://kazix.onrender.com';
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
    clearMatchingStorage(window.localStorage);
    clearMatchingStorage(window.sessionStorage);
    delete window.KaziXUser;
  }

  async function fetchProfile(token) {
    try {
      const res = await fetch(`${API_BASE}/v1/profiles/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
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
      window.location.replace('index.html');
    }
  }

  async function init() {
    renderGuest();

    const token = getToken();
    if (!token) return;

    const cachedProfile = getCachedProfile();
    if (cachedProfile) {
      window.KaziXUser = cachedProfile;
      renderSignedIn(cachedProfile);
    }

    const profile = await fetchProfile(token);
    if (!profile) {
      if (!cachedProfile) {
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
