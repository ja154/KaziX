/**
 * auth/send-otp.js
 * ─────────────────
 * Task 4 — Send a 6-digit OTP to a phone number via Supabase phone auth.
 * Delegates to the FastAPI /v1/auth/send-otp endpoint which calls Supabase.
 *
 * Works for both new sign-ups and returning users (same OTP flow).
 */

/**
 * @typedef {Object} OTPResult
 * @property {boolean} success
 * @property {string}  message
 * @property {string}  [error]   - set on failure
 */

/**
 * Sends an SMS OTP to the given phone number.
 *
 * @param {string} phone  - E.164 format: +254712345678
 * @returns {Promise<OTPResult>}
 */
export async function sendOTP(phone) {
  if (!/^\+254[0-9]{9}$/.test(phone)) {
    return {
      success: false,
      error:   'invalid_phone',
      message: 'Phone must be in format +254XXXXXXXXX',
    };
  }

  try {
    const response = await fetch('/v1/auth/send-otp', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ phone }),
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        success: false,
        error:   'send_failed',
        message: data.detail ?? 'Failed to send OTP. Please try again.',
      };
    }

    return { success: true, message: 'OTP sent successfully' };
  } catch (err) {
    return {
      success: false,
      error:   'network_error',
      message: 'Network error. Please check your connection.',
    };
  }
}
