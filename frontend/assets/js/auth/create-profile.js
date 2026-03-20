/**
 * auth/create-profile.js
 * ───────────────────────
 * Task 5 — Called from register.html on final form submission.
 *
 * Sends profile + optional fundi data to POST /v1/auth/profile.
 * Idempotent — safe to call multiple times (returns existing profile).
 */

/**
 * @typedef {Object} ProfileData
 * @property {string}               full_name
 * @property {string}               phone           +254XXXXXXXXX
 * @property {string}               [email]
 * @property {string}               county
 * @property {string}               [area]
 * @property {'client'|'fundi'}     role
 * @property {string}               [mpesa_number]
 * @property {'en'|'sw'}            [preferred_language]
 * @property {string}               [trade]           fundi only
 * @property {number}               [rate_min]        fundi only
 * @property {number}               [rate_max]        fundi only
 * @property {number}               [experience_years] fundi only
 * @property {string}               [bio]             fundi only
 */

/**
 * Creates or updates the user profile after OTP verification.
 *
 * @param {ProfileData} profileData
 * @param {string}      accessToken  - from verifyOTP result
 * @returns {Promise<{ success: boolean, profile?: object, error?: string, message?: string }>}
 */
export async function createProfile(profileData, accessToken) {
  if (!accessToken) {
    return { success: false, error: 'no_session', message: 'Not authenticated.' };
  }

  // Client-side validation before the round-trip
  if (!profileData.full_name?.trim()) {
    return { success: false, error: 'validation', message: 'Full name is required.' };
  }
  if (profileData.role === 'fundi' && !profileData.trade) {
    return { success: false, error: 'validation', message: 'Trade is required for fundi registration.' };
  }

  try {
    const response = await fetch('/v1/auth/profile', {
      method:  'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${accessToken}`,
      },
      body: JSON.stringify(profileData),
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        success: false,
        error:   'server_error',
        message: data.detail ?? 'Failed to save profile. Please try again.',
      };
    }

    return { success: true, profile: data.profile };
  } catch {
    return { success: false, error: 'network_error', message: 'Network error.' };
  }
}

/**
 * Convenience: reads register.html's form fields and calls createProfile.
 * Call this from register.html's submit button handler.
 *
 * @param {string} accessToken
 */
export async function submitRegistrationForm(accessToken) {
  // Map register.html field IDs to profile keys
  const get = (id) => document.getElementById(id)?.value?.trim() ?? '';

  const role = document.getElementById('typeClient')?.classList.contains('selected')
    ? 'client'
    : 'fundi';

  const profileData = {
    full_name:          get('regName')     || get('nameInput'),
    phone:              '+254' + get('regPhone').replace(/^0/, '').replace(/\s/g, ''),
    email:              get('regEmail')    || undefined,
    county:             get('regCounty')   || undefined,
    area:               get('regArea')     || undefined,
    role,
    mpesa_number:       undefined,
    preferred_language: 'en',
    // Fundi fields
    trade:              role === 'fundi' ? getSelectedTrade()          : undefined,
    rate_min:           role === 'fundi' ? parseInt(get('rateMin')) || undefined : undefined,
    rate_max:           role === 'fundi' ? parseInt(get('rateMax')) || undefined : undefined,
    experience_years:   role === 'fundi' ? parseInt(get('expYears')) || undefined : undefined,
    bio:                role === 'fundi' ? get('bioTextarea') || undefined : undefined,
  };

  return createProfile(profileData, accessToken);
}

function getSelectedTrade() {
  const selected = document.querySelector('.trade-chip.selected, .trade-option.selected');
  if (!selected) return undefined;
  // Extract trade key from text content
  const text = selected.querySelector('.t-name, .trade-chip')?.textContent
    ?? selected.textContent;
  const tradeMap = {
    'Plumber': 'plumber', 'Electrician': 'electrician', 'Mason': 'mason',
    'Mama Fua': 'mama_fua', 'Carpenter': 'carpenter', 'Painter': 'painter',
    'Roofer': 'roofer', 'Gardener': 'gardener', 'Driver/Mover': 'driver_mover',
    'Security': 'security',
  };
  for (const [label, key] of Object.entries(tradeMap)) {
    if (text.includes(label)) return key;
  }
  return 'other';
}
