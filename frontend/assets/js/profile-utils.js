(function () {
  const DEFAULT_REMOTE_API_BASE = 'https://kazix.onrender.com';

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

    if (isLocalHost(window.location.hostname)) {
      return window.location.origin.replace(/\/$/, '');
    }

    return DEFAULT_REMOTE_API_BASE;
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
  const DASHBOARD_STATE_STORAGE_KEY = 'kazix_dashboard_state';
  const DASHBOARD_STATE_MAX_AGE_MS = 60 * 1000;
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
    DASHBOARD_STATE_STORAGE_KEY,
  ]);
  const AUTH_STORAGE_PREFIXES = ['kazix_reg_'];
  const AUTH_REFRESH_BUFFER_MS = 60 * 1000;
  let myProfilePromise = null;
  let dashboardStatePromise = null;
  let refreshSessionPromise = null;

  function getAccessToken() {
    return localStorage.getItem('kazix_access_token');
  }

  function getRefreshToken() {
    return localStorage.getItem('kazix_refresh_token');
  }

  function getStoredExpiresAtSeconds() {
    const value = Number(localStorage.getItem('kazix_expires_at'));
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

  function persistSessionTokens(payload) {
    if (!payload?.access_token) return null;

    const expiresIn = Number(payload.expires_in);
    const expiresAt = computeExpiresAtSeconds(payload);

    localStorage.setItem('kazix_access_token', payload.access_token);
    if (payload.refresh_token) {
      localStorage.setItem('kazix_refresh_token', payload.refresh_token);
    }
    if (Number.isFinite(expiresIn) && expiresIn > 0) {
      localStorage.setItem('kazix_expires_in', String(Math.floor(expiresIn)));
    } else {
      localStorage.removeItem('kazix_expires_in');
    }
    if (expiresAt !== null) {
      localStorage.setItem('kazix_expires_at', String(expiresAt));
    } else {
      localStorage.removeItem('kazix_expires_at');
    }
    localStorage.setItem(
      'kazix_token_type',
      payload.token_type || localStorage.getItem('kazix_token_type') || 'bearer'
    );

    return payload.access_token;
  }

  function shouldRefreshAccessToken() {
    const expiresAtMs = getStoredExpiresAtMs();
    return Boolean(
      getAccessToken()
      && getRefreshToken()
      && expiresAtMs
      && expiresAtMs <= (Date.now() + AUTH_REFRESH_BUFFER_MS)
    );
  }

  async function refreshAccessToken(options = {}) {
    const { force = false } = options;
    const currentToken = getAccessToken();
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
      const resp = await fetch(`${API_BASE}/v1/auth/oauth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      const text = await resp.text();
      const data = text ? safeJson(text) : {};

      if (!resp.ok || !data?.access_token) {
        const error = new Error(
          data?.detail || text || `Could not refresh session (${resp.status})`
        );
        error.status = resp.status;
        if (resp.status === 400 || resp.status === 401) {
          clearAuthStorage();
        }
        throw error;
      }

      return persistSessionTokens(data);
    })().finally(() => {
      refreshSessionPromise = null;
    });

    return refreshSessionPromise;
  }

  async function getValidAccessToken(options = {}) {
    const { forceRefresh = false } = options;
    const currentToken = getAccessToken();
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
      return getAccessToken() || currentToken;
    }
  }

  function getProfileIdFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const value = (params.get('id') || '').trim();
    return value || null;
  }

  async function requestJson(path, options = {}) {
    const {
      auth = false,
      method = 'GET',
      body,
      showSuccess = false,
      showError = true,
      _retryAuth = false,
    } = options;
    const headers = {};
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    if (auth) {
      const token = await getValidAccessToken();
      if (!token) {
        if (window.KazixErrorHandler) {
          window.KazixErrorHandler.showError('Please sign in to access your profile.');
        }
        throw new Error('Please sign in to access your profile.');
      }
      headers.Authorization = `Bearer ${token}`;
    }

    try {
      const resp = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });

      const text = await resp.text();
      const data = text ? safeJson(text) : {};

      if (auth && resp.status === 401 && !_retryAuth) {
        const refreshedToken = await getValidAccessToken({ forceRefresh: true });
        if (refreshedToken) {
          return requestJson(path, {
            ...options,
            _retryAuth: true,
          });
        }
        clearAuthStorage();
      }

      if (!resp.ok) {
        if (auth && resp.status === 401) {
          clearAuthStorage();
        }

        // Prepare error info for display
        const errorInfo = {
          status: resp.status,
          detail: data?.detail || data?.message,
          message: text,
        };

        // Show error to user if requested
        if (showError && window.KazixErrorHandler) {
          const msgConfig = window.KazixErrorMessages?.mapApiError(errorInfo);
          if (msgConfig) {
            window.KazixErrorHandler.showError(msgConfig.message, { 
              title: msgConfig.title,
              duration: 5000
            });

            // Handle validation errors - extract field errors
            if (resp.status === 422 && data?.detail) {
              const fieldErrors = window.KazixErrorMessages?.extractValidationErrors(data);
              if (fieldErrors && Object.keys(fieldErrors).length > 0) {
                Object.entries(fieldErrors).forEach(([field, error]) => {
                  window.KazixErrorHandler.setFieldError(field, error);
                });
              }
            }

            // Redirect if auth error
            if ((resp.status === 401 || resp.status === 403) && msgConfig.shouldRedirect) {
              setTimeout(() => {
                window.location.href = msgConfig.redirectTo || 'login.html';
              }, 1500);
            }
          }
        }

        // Create error object for caller
        const message = data?.detail || data?.message || text || `Request failed (${resp.status})`;
        const error = new Error(message);
        error.status = resp.status;
        error.detail = data?.detail;
        throw error;
      }

      // Show success message if requested
      if (showSuccess && window.KazixErrorHandler) {
        const successMsg = typeof showSuccess === 'string' ? showSuccess : 'Operation completed successfully';
        window.KazixErrorHandler.showSuccess(successMsg);
      }

      return data;
    } catch (error) {
      // Network or other errors
      if (showError && window.KazixErrorHandler) {
        if (error instanceof TypeError && error.message.includes('fetch')) {
          window.KazixErrorHandler.showError('Unable to reach the server. Please check your connection.', {
            title: 'Connection Error',
            duration: 5000
          });
        } else if (!(error instanceof Error) || !error.status) {
          // Only show if it's not an HTTP error (those are handled above)
          if (!error.message?.includes('sign in') && !error.message?.includes('401')) {
            window.KazixErrorHandler.showError(error.message || 'An unexpected error occurred', {
              duration: 5000
            });
          }
        }
      }
      throw error;
    }
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

  function buildPagePath(page, params = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      const normalized = String(value).trim();
      if (!normalized) return;
      search.set(key, normalized);
    });
    const query = search.toString();
    return query ? `${page}?${query}` : page;
  }

  function buildMessagesPath(options = {}) {
    return buildPagePath('messages.html', {
      participant: options.participantId || options.participant || null,
      job: options.jobId || options.job || null,
      application: options.applicationId || options.application || null,
      booking: options.bookingId || options.booking || null,
    });
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
    dashboardStatePromise = null;
    refreshSessionPromise = null;
    clearMatchingStorage(window.localStorage);
    clearMatchingStorage(window.sessionStorage);
  }

  function readCachedDashboardState(maxAgeMs) {
    try {
      const raw = window.sessionStorage.getItem(DASHBOARD_STATE_STORAGE_KEY);
      if (!raw) return null;

      const parsed = safeJson(raw);
      if (!parsed || !parsed.data || !parsed.saved_at) {
        return null;
      }

      if ((Date.now() - Number(parsed.saved_at)) > (maxAgeMs || DASHBOARD_STATE_MAX_AGE_MS)) {
        return null;
      }

      return parsed.data;
    } catch (_error) {
      return null;
    }
  }

  function writeCachedDashboardState(data) {
    try {
      window.sessionStorage.setItem(DASHBOARD_STATE_STORAGE_KEY, JSON.stringify({
        saved_at: Date.now(),
        data,
      }));
    } catch (_error) {
      // Ignore storage errors; the state can still live in memory for this page.
    }
  }

  function clearDashboardStateCache() {
    dashboardStatePromise = null;
    try {
      window.sessionStorage.removeItem(DASHBOARD_STATE_STORAGE_KEY);
    } catch (_error) {
      // Ignore storage cleanup failures.
    }
  }

  function findNavLinks(href) {
    return Array.from(document.querySelectorAll(`.nav-item[href="${href}"]`));
  }

  function ensureBadge(link) {
    if (!link) return null;
    var badge = link.querySelector('.ni-badge');
    if (badge) return badge;

    badge = document.createElement('span');
    badge.className = 'ni-badge';
    link.appendChild(badge);
    return badge;
  }

  function setNavBadge(href, value) {
    findNavLinks(href).forEach(function (link) {
      var badge = ensureBadge(link);
      if (!badge) return;
      badge.textContent = String(value);
    });
  }

  function clearNavBadge(href) {
    findNavLinks(href).forEach(function (link) {
      var badge = link.querySelector('.ni-badge');
      if (badge) {
        badge.remove();
      }
    });
  }

  function applyDashboardNavState(state) {
    if (!state || !state.role) return;

    if (state.role === 'client') {
      setNavBadge('my-jobs.html', state.nav?.jobs ?? 0);
      setNavBadge('job-applicants.html', state.nav?.applications ?? 0);
      setNavBadge('my-hires.html', state.nav?.hires ?? 0);
      clearNavBadge('saved-workers.html');
      clearNavBadge('messages.html');
      return;
    }

    if (state.role === 'fundi') {
      setNavBadge('worker-jobs.html', state.nav?.find_jobs ?? 0);
      setNavBadge('my-applications.html', state.nav?.applications ?? 0);
      setNavBadge('worker-hires.html', state.nav?.contracts ?? 0);
      clearNavBadge('messages.html');
    }
  }

  async function getDashboardState(options = {}) {
    const { force = false, silent = true, maxAgeMs = DASHBOARD_STATE_MAX_AGE_MS } = options;

    if (!getAccessToken()) {
      return Promise.reject(new Error('Please sign in to access your dashboard.'));
    }

    if (!force) {
      const cached = readCachedDashboardState(maxAgeMs);
      if (cached) {
        applyDashboardNavState(cached);
        return cached;
      }
    }

    if (!force && dashboardStatePromise) {
      return dashboardStatePromise;
    }

    dashboardStatePromise = requestJson('/v1/dashboard/state', {
      auth: true,
      showError: !silent,
    }).then((data) => {
      writeCachedDashboardState(data);
      applyDashboardNavState(data);
      if (typeof window.CustomEvent === 'function') {
        window.dispatchEvent(new CustomEvent('kazix:dashboard-state', { detail: data }));
      }
      return data;
    }).catch((error) => {
      dashboardStatePromise = null;
      throw error;
    });

    return dashboardStatePromise;
  }

  async function hydrateDashboardState(options = {}) {
    const { silent = true } = options;
    try {
      return await getDashboardState(options);
    } catch (error) {
      if (!silent) throw error;
      return null;
    }
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
      hydrateDashboardState({ silent: true });

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
    getValidAccessToken,
    getDashboardState,
    getMyProfile,
    getProfileIdFromQuery,
    hydrateDashboardState,
    hydrateShell,
    initials,
    logout,
    profilePath,
    refreshAccessToken,
    requestJson,
    roleHomePath,
    roleLabel,
    clearDashboardStateCache,
    buildMessagesPath,
    buildPagePath,
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
