(function () {
  function resolveApiBase() {
    const configured = String(window.KAZIX_API_BASE || window.KAZIX_CONFIG?.KAZIX_API_BASE || '').trim();
    const host = window.location.hostname;
    const proxyHosts = new Set([
      'kazixfrontend.vercel.app',
      'kazix.vercel.app',
      'kazix.co.ke',
      'www.kazix.co.ke',
    ]);
    const useSameOriginProxy = proxyHosts.has(host) || host.endsWith('.kazix.co.ke');

    if (configured) {
      try {
        const configuredUrl = new URL(configured, window.location.origin);
        if (configuredUrl.origin === window.location.origin && configuredUrl.pathname === '/') {
          return '';
        }
        return configuredUrl.toString().replace(/\/$/, '');
      } catch (_error) {
        return configured.replace(/\/$/, '');
      }
    }

    if (useSameOriginProxy) {
      return '';
    }

    return window.location.origin.replace(/\/$/, '');
  }

  const API_BASE = resolveApiBase();

  const TRADE_LABELS = {
    plumber: 'Plumber',
    electrician: 'Electrician',
    mason: 'Mason',
    mama_fua: 'Mama Fua',
    carpenter: 'Carpenter',
    painter: 'Painter',
    roofer: 'Roofer',
    gardener: 'Gardener',
    driver_mover: 'Driver / Mover',
    security: 'Security',
    other: 'Skilled Worker',
  };
  const ROLE_HOME_PATHS = {
    client: 'client-profile.html',
    fundi: 'worker-profile-edit.html',
    admin: 'admin-dashboard.html',
  };
  const AUTH_STORAGE_KEYS = new Set([
    'kazix_access_token',
    'kazix_refresh_token',
    'kazix_expires_in',
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
  ]);
  const AUTH_STORAGE_PREFIXES = ['kazix_reg_'];
  let myProfilePromise = null;

  function getAccessToken() {
    return localStorage.getItem('kazix_access_token');
  }

  function getProfileIdFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const value = (params.get('id') || '').trim();
    return value || null;
  }

  async function requestJson(path, options = {}) {
    const { auth = false, method = 'GET', body } = options;
    const headers = {};
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    if (auth) {
      const token = getAccessToken();
      if (!token) {
        throw new Error('Please sign in to access your profile.');
      }
      headers.Authorization = `Bearer ${token}`;
    }

    const resp = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const text = await resp.text();
    const data = text ? safeJson(text) : {};
    if (!resp.ok) {
      const message = data?.detail || data?.message || text || `Request failed (${resp.status})`;
      throw new Error(message);
    }
    return data;
  }

  function getMyProfile(options = {}) {
    if (options.force) {
      myProfilePromise = null;
    }

    if (!getAccessToken()) {
      return Promise.reject(new Error('Please sign in to access your profile.'));
    }

    if (!myProfilePromise) {
      myProfilePromise = requestJson('/v1/profiles/me', { auth: true }).catch((error) => {
        myProfilePromise = null;
        
        // Handle 404 Profile not found — user hasn't completed registration yet.
        // We do NOT clear the auth tokens here, as the user IS authenticated with Supabase,
        // they just don't have a KaziX profile record yet.
        if (error.message && (error.message.includes('404') || error.message.includes('Profile not found'))) {
          const redirectUrl = 'register.html?mode=complete-profile';
          console.warn('Profile not found for authenticated user. Redirecting to registration:', error.message);
          window.location.replace(redirectUrl);
          
          // Return a rejected promise in case redirect is blocked
          return Promise.reject(new Error('Profile not found. Please complete your registration.'));
        }
        
        throw error;
      });
    }

    return myProfilePromise;
  }

  function safeJson(text) {
    try {
      return JSON.parse(text);
    } catch (_err) {
      return null;
    }
  }

  function profilePath(role, userId) {
    if (!userId) return '#';
    if (role === 'client') {
      return `client-public-profile.html?id=${encodeURIComponent(userId)}`;
    }
    return `worker-profile.html?id=${encodeURIComponent(userId)}`;
  }

  function formatTrade(value) {
    return TRADE_LABELS[value] || 'Skilled Worker';
  }

  function formatLocation(profile) {
    const parts = [profile?.area, profile?.county].filter(Boolean);
    return parts.length ? parts.join(', ') : 'Location not added yet';
  }

  function formatMemberSince(value) {
    if (!value) return 'New member';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'New member';
    return `Member since ${date.toLocaleDateString(undefined, {
      month: 'long',
      year: 'numeric',
    })}`;
  }

  function formatLanguage(value) {
    if (value === 'sw') return 'Swahili';
    if (value === 'en') return 'English';
    return 'Not set';
  }

  function formatCurrency(value) {
    if (value === null || value === undefined || value === '') return 'Not set';
    return `KES ${Number(value).toLocaleString()}`;
  }

  function formatPhone(value) {
    if (!value) return 'Not set';
    const cleaned = String(value).replace(/[^\d+]/g, '');
    if (/^\+254\d{9}$/.test(cleaned)) {
      return `${cleaned.slice(0, 4)} ${cleaned.slice(4, 7)} ${cleaned.slice(7, 10)} ${cleaned.slice(10)}`;
    }
    return value;
  }

  function initials(name) {
    const parts = String(name || '')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2);
    if (!parts.length) return 'KX';
    return parts.map((part) => part[0].toUpperCase()).join('');
  }

  function arrayToCsv(value) {
    return Array.isArray(value) ? value.join(', ') : '';
  }

  function csvToArray(value) {
    return String(value || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setText(target, value) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return;
    el.textContent = value ?? '';
  }

  function setHtml(target, value) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return;
    el.innerHTML = value ?? '';
  }

  function setAllText(selector, value) {
    document.querySelectorAll(selector).forEach((el) => {
      el.textContent = value ?? '';
    });
  }

  function show(target, visible) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return;
    el.style.display = visible ? '' : 'none';
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function roleHomePath(role) {
    return ROLE_HOME_PATHS[role] || 'index.html';
  }

  function roleLabel(role, fundiProfile) {
    if (role === 'fundi') {
      const tradeLabel = fundiProfile?.trade ? formatTrade(fundiProfile.trade) : null;
      return tradeLabel ? `Pro account · ${tradeLabel}` : 'Pro account';
    }
    if (role === 'admin') return 'Admin account';
    return 'Client account';
  }

  function setDestination(target, href) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el || !href) return;

    if (el.tagName === 'A') {
      el.setAttribute('href', href);
      return;
    }

    el.style.cursor = 'pointer';
    el.onclick = function () {
      window.location.href = href;
    };
  }

  function wireNotificationButtons() {
    document.querySelectorAll('.notif-btn').forEach((button) => {
      if (button.dataset.notificationsWired === 'true') return;

      button.dataset.notificationsWired = 'true';
      button.style.cursor = 'pointer';

      if (!button.getAttribute('aria-label')) {
        button.setAttribute('aria-label', 'View notifications');
      }

      button.addEventListener('click', function () {
        window.location.href = 'notifications.html';
      });
    });
  }

  function isSupabaseStorageKey(key) {
    return key === 'supabase.auth.token'
      || /^sb-[a-z0-9_-]+-auth-token(?:-code-verifier)?$/i.test(key);
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

  function clearAuthStorage() {
    myProfilePromise = null;
    clearMatchingStorage(window.localStorage);
    clearMatchingStorage(window.sessionStorage);
  }

  async function hydrateShell(options = {}) {
    const { data = null, silent = true } = options;

    try {
      const shellData = data || await getMyProfile();
      const profile = shellData?.profile || {};
      const fundiProfile = shellData?.fundi_profile || {};
      if (!profile.id) return null;

      const name = profile.full_name || profile.email || formatPhone(profile.phone) || 'My account';
      const avatar = initials(name);
      const accountLabel = roleLabel(profile.role, fundiProfile);
      const accountHref = roleHomePath(profile.role);

      setAllText('.topnav .user-avatar', avatar);
      setAllText('.topnav .user-name', name);
      setAllText('.sidebar-bottom .sp-avatar', avatar);
      setAllText('.sidebar-bottom .sp-name', name);
      setAllText('.sidebar-bottom .sp-role', accountLabel);
      setDestination('.topnav .user-chip', accountHref);
      setDestination('.sidebar-bottom .sidebar-profile', accountHref);
      wireNotificationButtons();

      return shellData;
    } catch (error) {
      if (!silent) throw error;
      return null;
    }
  }

  async function logout() {
    try {
      const token = getAccessToken();
      if (token) {
        await requestJson('/v1/auth/logout', { auth: true, method: 'POST' });
      }
    } catch (error) {
      console.warn('Logout request failed:', error);
    } finally {
      clearAuthStorage();

      // Replace the current history entry so the user cannot bounce back into
      // an authenticated page after logging out.
      window.location.replace('login.html?logged_out=1');
    }
  }

  window.KazixProfile = {
    API_BASE,
    arrayToCsv,
    csvToArray,
    escapeHtml,
    formatCurrency,
    formatLanguage,
    formatLocation,
    formatMemberSince,
    formatPhone,
    formatTrade,
    getAccessToken,
    getMyProfile,
    getProfileIdFromQuery,
    hydrateShell,
    initials,
    logout,
    profilePath,
    requestJson,
    roleHomePath,
    roleLabel,
    setHtml,
    setText,
    show,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireNotificationButtons);
  } else {
    wireNotificationButtons();
  }
})();
