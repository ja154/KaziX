/**
 * api/client.js
 * ─────────────
 * Small fetch wrapper for calling FastAPI routes from page scripts.
 */

import { requireAuth } from '../auth/session.js';

export async function apiRequest(path, options = {}) {
  const {
    method = 'GET',
    body,
    headers = {},
    requireSession = true,
  } = options;

  let token = null;
  if (requireSession) {
    const session = await requireAuth();
    token = session?.access_token ?? null;
  }

  const finalHeaders = {
    'Content-Type': 'application/json',
    ...headers,
  };
  if (token) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(path, {
    method,
    headers: finalHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const raw = await response.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = { detail: raw };
    }
  }

  if (!response.ok) {
    const message = payload?.detail || `Request failed with status ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function formatTimeAgo(isoString) {
  if (!isoString) return 'just now';
  const ts = new Date(isoString).getTime();
  if (Number.isNaN(ts)) return 'just now';

  const deltaSeconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (deltaSeconds < 60) return 'just now';
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)}m ago`;
  if (deltaSeconds < 86400) return `${Math.floor(deltaSeconds / 3600)}h ago`;
  if (deltaSeconds < 604800) return `${Math.floor(deltaSeconds / 86400)}d ago`;

  return new Date(isoString).toLocaleDateString('en-KE', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}
