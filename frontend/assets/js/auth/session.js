/**
 * auth/session.js
 * ────────────────
 * Task 4 — Session management helpers for all authenticated pages.
 *
 * Exports:
 *   requireAuth(redirectTo?)   → redirects to login if no session
 *   requireRole(role, redirectTo?) → additionally checks user role
 *   getSession()               → returns { user, profile } in one call
 */

import { supabase } from '../supabase/client.js';

const LOGIN_URL = '/login.html';

/**
 * Checks for an active Supabase session.
 * Redirects to login.html (or redirectTo) if none exists.
 *
 * Call at the top of every authenticated page's <script>:
 *   await requireAuth();
 *
 * @param {string} [redirectTo='/login.html']
 * @returns {Promise<import('@supabase/supabase-js').Session>}
 */
export async function requireAuth(redirectTo = LOGIN_URL) {
  const { data: { session }, error } = await supabase.auth.getSession();

  if (error || !session) {
    // Preserve the current URL so login can redirect back after auth
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.replace(`${redirectTo}?return=${returnUrl}`);
    // Return a never-resolving promise so the page script halts here
    return new Promise(() => {});
  }

  return session;
}

/**
 * Checks for an active session AND that the user's profile role matches.
 * Redirects to redirectTo if either check fails.
 *
 * @param {'client'|'fundi'|'admin'} role
 * @param {string} [redirectTo='/login.html']
 * @returns {Promise<{ session: Session, profile: object }>}
 */
export async function requireRole(role, redirectTo = LOGIN_URL) {
  const session = await requireAuth(redirectTo);

  const { user, profile } = await getSession();
  if (!profile || profile.role !== role) {
    // Wrong role — redirect to their correct dashboard
    const dashboardMap = {
      client: '/client-dashboard.html',
      fundi:  '/worker-dashboard.html',
      admin:  '/admin-dashboard.html',
    };
    const dest = dashboardMap[profile?.role] ?? redirectTo;
    window.location.replace(dest);
    return new Promise(() => {});
  }

  return { session, profile };
}

/**
 * Returns the current authenticated user and their full profiles row.
 * Makes a single API call to the FastAPI /v1/auth/session endpoint.
 *
 * @returns {Promise<{ user: object|null, profile: object|null }>}
 */
export async function getSession() {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return { user: null, profile: null };

  try {
    const resp = await fetch('/v1/auth/session', {
      headers: {
        'Authorization': `Bearer ${session.access_token}`,
        'Content-Type':  'application/json',
      },
    });

    if (!resp.ok) return { user: session.user, profile: null };

    const profile = await resp.json();
    return { user: session.user, profile };
  } catch {
    return { user: session.user, profile: null };
  }
}

/**
 * Signs the user out and redirects to the homepage.
 */
export async function signOut() {
  await supabase.auth.signOut();
  window.location.replace('/index.html');
}
