/**
 * auth/verify-otp.js
 * ───────────────────
 * Task 4 — Verifies the 6-digit OTP token.
 *
 * On success:
 *   - Stores the Supabase session tokens
 *   - Checks is_new_user flag from API
 *   - Redirects to profile completion or the correct dashboard
 */

/**
 * @typedef {Object} VerifyResult
 * @property {boolean}       success
 * @property {string}        [error]
 * @property {string}        [message]
 * @property {boolean}       [is_new_user]
 * @property {string}        [redirect_to]
 * @property {string}        [access_token]
 * @property {string}        [refresh_token]
 */

/**
 * Verifies the OTP and handles post-auth routing.
 *
 * @param {string} phone   - E.164: +254712345678
 * @param {string} token   - 6-digit OTP string
 * @param {boolean} [autoRedirect=true]  - set false to suppress redirect
 * @returns {Promise<VerifyResult>}
 */
export async function verifyOTP(phone, token, autoRedirect = true) {
  if (!/^\d{6}$/.test(token)) {
    return { success: false, error: 'invalid_token', message: 'Enter the 6-digit code' };
  }

  let data;
  try {
    const response = await fetch('/v1/auth/verify-otp', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ phone, token }),
    });

    data = await response.json();

    if (!response.ok) {
      return {
        success: false,
        error:   'invalid_otp',
        message: data.detail ?? 'Invalid or expired OTP. Please try again.',
      };
    }
  } catch {
    return { success: false, error: 'network_error', message: 'Network error.' };
  }

  // Store tokens for subsequent API calls
  // (Supabase JS client also stores its own copy via supabase.auth.setSession)
  if (data.access_token) {
    sessionStorage.setItem('kx_access_token',  data.access_token);
    sessionStorage.setItem('kx_refresh_token', data.refresh_token);

    // Sync the Supabase JS client so it uses the new session
    const { supabase } = await import('../supabase/client.js');
    await supabase.auth.setSession({
      access_token:  data.access_token,
      refresh_token: data.refresh_token,
    });
  }

  if (autoRedirect) {
    const dashboardMap = {
      'client-dashboard': '/client-dashboard.html',
      'fundi-dashboard':  '/worker-dashboard.html',
      'admin-dashboard':  '/admin-dashboard.html',
    };

    if (data.is_new_user) {
      window.location.replace('/register.html?step=profile');
    } else {
      const dest = dashboardMap[data.redirect_to] ?? '/client-dashboard.html';
      // Honour return URL if present
      const params      = new URLSearchParams(window.location.search);
      const returnUrl   = params.get('return');
      window.location.replace(returnUrl ? decodeURIComponent(returnUrl) : dest);
    }
  }

  return {
    success:       true,
    is_new_user:   data.is_new_user,
    redirect_to:   data.redirect_to,
    access_token:  data.access_token,
    refresh_token: data.refresh_token,
  };
}
