import { apiRequest, escapeHtml } from '../api/client.js';

const state = {
  profile: null,
};

function initials(name) {
  const parts = String(name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (!parts.length) return 'U';
  return parts.map((p) => p[0].toUpperCase()).join('');
}

function setInfoValue(label, value) {
  const items = document.querySelectorAll('.info-item');
  items.forEach((item) => {
    const key = item.querySelector('.info-label')?.textContent?.trim()?.toLowerCase();
    if (key === label.toLowerCase()) {
      const node = item.querySelector('.info-val');
      if (node) node.textContent = value ?? '—';
    }
  });
}

function applyProfile(profile) {
  state.profile = profile;

  const name = profile.full_name || 'User';
  const county = profile.county || '';
  const area = profile.area || '';
  const location = [area, county].filter(Boolean).join(', ') || 'Location not set';

  const topName = document.querySelector('.topnav .user-name');
  if (topName) topName.textContent = name;

  const topAvatar = document.querySelector('.topnav .user-avatar');
  if (topAvatar) topAvatar.textContent = initials(name);

  const profileName = document.querySelector('.p-name');
  if (profileName) profileName.textContent = name;

  const profileType = document.querySelector('.p-type');
  if (profileType) profileType.textContent = `${profile.role || 'client'} · Employer`;

  const profileLocation = document.querySelector('.p-location');
  if (profileLocation) profileLocation.textContent = `📍 ${location}`;

  const member = document.querySelector('.p-member');
  if (member && profile.created_at) {
    const date = new Date(profile.created_at).toLocaleDateString('en-KE', {
      month: 'long',
      year: 'numeric',
    });
    member.textContent = `Member since ${date}`;
  }

  setInfoValue('Phone', profile.phone || '—');
  setInfoValue('Email', profile.email || '—');
  setInfoValue('County', profile.county || '—');
  setInfoValue('Area', profile.area || '—');
  setInfoValue('M-Pesa Number', profile.mpesa_number || profile.phone || '—');
  setInfoValue(
    'Preferred Language',
    profile.preferred_language === 'sw' ? 'Swahili' : 'English',
  );
}

async function reloadProfile() {
  const data = await apiRequest('/v1/profiles/me');
  if (data?.profile) applyProfile(data.profile);
}

window.toggleEdit = async () => {
  if (!state.profile) return;

  const fullName = window.prompt('Full name', state.profile.full_name || '');
  if (fullName === null) return;

  const county = window.prompt('County', state.profile.county || '');
  if (county === null) return;

  const area = window.prompt('Area', state.profile.area || '');
  if (area === null) return;

  const email = window.prompt('Email (optional)', state.profile.email || '');
  if (email === null) return;

  const mpesa = window.prompt('M-Pesa number', state.profile.mpesa_number || state.profile.phone || '');
  if (mpesa === null) return;

  try {
    const payload = {
      full_name: fullName.trim(),
      county: county.trim() || null,
      area: area.trim() || null,
      email: email.trim() || null,
      mpesa_number: mpesa.trim() || null,
    };
    const updated = await apiRequest('/v1/profiles/me', {
      method: 'PATCH',
      body: payload,
    });
    if (updated?.profile) applyProfile(updated.profile);
    alert('Profile updated.');
  } catch (error) {
    alert(error.message || 'Failed to update profile.');
  }
};

// Keep existing inline helper semantics but avoid breaking current markup.
window.saveField = (fieldId) => {
  const field = document.getElementById(fieldId);
  if (field) field.style.display = 'none';
};

window.toggleField = (id) => {
  const element = document.getElementById(id);
  if (!element) return;
  element.style.display = element.style.display === 'none' ? 'block' : 'none';
};

reloadProfile().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Failed to load profile:', escapeHtml(error.message));
});
