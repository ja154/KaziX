/**
 * auth-session.js
 * Utilities for managing authentication sessions, tokens, and auto-refresh
 * Import this on every authenticated page
 */

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
const SESSION_KEYS = {
  access_token: 'kazix_access_token',
  refresh_token: 'kazix_refresh_token',
  expires_in: 'kazix_expires_in',
  token_type: 'kazix_token_type',
  expires_at: 'kazix_expires_at',
};

let refreshTimer = null;

/**
 * Get the current access token from localStorage
 */
function getAccessToken() {
  return localStorage.getItem(SESSION_KEYS.access_token);
}

/**
 * Get the refresh token from localStorage
 */
function getRefreshToken() {
  return localStorage.getItem(SESSION_KEYS.refresh_token);
}

/**
 * Get authorization headers for API requests
 */
function getAuthHeaders() {
  const token = getAccessToken();
  if (!token) return {};
  
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
}

/**
 * Check if access token is valid and not expired
 */
function isTokenValid() {
  const accessToken = getAccessToken();
  const expiresAt = localStorage.getItem(SESSION_KEYS.expires_at);
  
  if (!accessToken || !expiresAt) return false;
  
  const expiresAtTime = Number(expiresAt);
  const now = Date.now();
  
  return now < expiresAtTime;
}

/**
 * Schedule automatic token refresh before expiry
 * Refreshes 5 minutes before token expires
 */
function scheduleTokenRefresh(expiresIn) {
  if (refreshTimer) clearTimeout(refreshTimer);
  
  // Refresh 5 minutes before expiry (300,000 ms)
  const refreshTime = Math.max(0, (expiresIn - 300) * 1000);
  
  refreshTimer = setTimeout(async () => {
    console.log('[Auth] Scheduling automatic token refresh...');
    try {
      await refreshAccessToken();
      console.log('[Auth] Token refreshed automatically');
    } catch (err) {
      console.error('[Auth] Automatic token refresh failed:', err);
      // If refresh fails, redirect to login
      clearSession();
      window.location.href = '/pages/login.html';
    }
  }, refreshTime);
}

/**
 * Refresh access token using refresh token
 */
async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  console.log('[Auth] Refreshing access token...');
  const resp = await fetch(`${API_BASE}/v1/auth/oauth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
  });

  if (!resp.ok) {
    throw new Error(`Token refresh failed: ${resp.status} ${resp.statusText}`);
  }

  const data = await resp.json();
  
  // Store new tokens
  localStorage.setItem(SESSION_KEYS.access_token, data.access_token);
  localStorage.setItem(SESSION_KEYS.refresh_token, data.refresh_token);
  localStorage.setItem(SESSION_KEYS.token_type, data.token_type || 'bearer');
  
  const expiresIn = data.expires_in || 3600;
  localStorage.setItem(SESSION_KEYS.expires_in, String(expiresIn));
  localStorage.setItem(SESSION_KEYS.expires_at, String(Date.now() + expiresIn * 1000));
  
  // Schedule next refresh
  scheduleTokenRefresh(expiresIn);
  
  return data;
}

/**
 * Validate session on page load
 * Redirects to login if token is invalid/expired
 */
function validateSession() {
  const accessToken = getAccessToken();
  const expiresAt = localStorage.getItem(SESSION_KEYS.expires_at);
  const refreshToken = getRefreshToken();
  
  // No token at all - redirect to login
  if (!accessToken || !refreshToken) {
    console.log('[Auth] No tokens found, redirecting to login');
    window.location.href = '/pages/login.html';
    return false;
  }
  
  // Token expired - try to refresh
  if (expiresAt && Date.now() > Number(expiresAt)) {
    console.log('[Auth] Token expired, attempting refresh...');
    refreshAccessToken().catch(() => {
      window.location.href = '/pages/login.html';
    });
    return false;
  }
  
  // Token is valid
  return true;
}

/**
 * Make authenticated API request
 */
async function fetchProtected(url, options = {}) {
  // Validate session first
  if (!validateSession()) {
    throw new Error('Session invalid - user redirected to login');
  }

  const resp = await fetch(url, {
    ...options,
    headers: {
      ...getAuthHeaders(),
      ...options.headers
    }
  });

  // If 401, token might have been revoked - redirect to login
  if (resp.status === 401) {
    clearSession();
    window.location.href = '/pages/login.html';
    throw new Error('Session expired - user redirected to login');
  }

  return resp;
}

/**
 * Clear all session data
 */
function clearSession() {
  Object.values(SESSION_KEYS).forEach(key => {
    localStorage.removeItem(key);
  });
  localStorage.removeItem('kazix_reg_pending_profile');
  if (refreshTimer) clearTimeout(refreshTimer);
}

/**
 * Log out user
 */
async function logout() {
  try {
    await fetch(`${API_BASE}/v1/auth/logout`, {
      method: 'POST',
      headers: getAuthHeaders()
    });
  } catch (err) {
    console.warn('[Auth] Logout API failed:', err);
  }
  
  clearSession();
  window.location.href = '/pages/login.html';
}

/**
 * Initialize session on page load
 * Call this on every protected page
 */
function initializeSession() {
  // Validate token is present and not expired
  if (!validateSession()) {
    return;
  }

  // Schedule auto-refresh
  const expiresIn = Number(localStorage.getItem(SESSION_KEYS.expires_in)) || 3600;
  scheduleTokenRefresh(expiresIn);

  // Log session initialized
  console.log('[Auth] Session initialized');
}

// Auto-initialize on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeSession);
} else {
  initializeSession();
}
