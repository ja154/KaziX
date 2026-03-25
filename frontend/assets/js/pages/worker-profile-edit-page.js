import { apiRequest } from '../api/client.js';

const state = {
  profile: null,
  fundiProfile: null,
};

function initials(name) {
  const parts = String(name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (!parts.length) return 'U';
  return parts.map((p) => p[0].toUpperCase()).join('');
}

function normalizeSkill(value) {
  return String(value || '')
    .replace(/[^\w\s]/g, '')
    .trim()
    .toLowerCase();
}

function applyProfile(profile, fundiProfile) {
  state.profile = profile || null;
  state.fundiProfile = fundiProfile || null;

  const name = profile?.full_name || 'Worker';
  const county = profile?.county || '';
  const area = profile?.area || '';
  const location = [area, county].filter(Boolean).join(', ') || 'Location not set';

  const topName = document.querySelector('.topnav .user-name');
  if (topName) topName.textContent = name;

  const topAvatar = document.querySelector('.topnav .user-avatar');
  if (topAvatar) topAvatar.textContent = initials(name);

  const pName = document.querySelector('.p-name');
  if (pName) pName.textContent = name;

  const pType = document.querySelector('.p-type');
  if (pType) {
    const trade = fundiProfile?.trade || 'Fundi';
    pType.textContent = `${trade} · Pro`;
  }

  const pLocation = document.querySelector('.p-location');
  if (pLocation) pLocation.textContent = `📍 ${location}`;

  const bioView = document.querySelector('#bioV .bio-text');
  if (bioView && fundiProfile?.bio) bioView.textContent = fundiProfile.bio;

  const bioInput = document.querySelector('#bioF textarea');
  if (bioInput && fundiProfile?.bio) bioInput.value = fundiProfile.bio;

  const rateInputs = document.querySelectorAll('.rate-input');
  if (rateInputs[0] && fundiProfile?.rate_min !== undefined && fundiProfile.rate_min !== null) {
    rateInputs[0].value = fundiProfile.rate_min;
  }
  if (rateInputs[1] && fundiProfile?.rate_max !== undefined && fundiProfile.rate_max !== null) {
    rateInputs[1].value = fundiProfile.rate_max;
  }

  if (Array.isArray(fundiProfile?.skills) && fundiProfile.skills.length > 0) {
    const enabled = new Set(fundiProfile.skills.map(normalizeSkill));
    document.querySelectorAll('.skill-chip').forEach((chip) => {
      const key = normalizeSkill(chip.textContent);
      chip.classList.toggle('on', enabled.has(key));
    });
  }
}

function collectSkills() {
  return Array.from(document.querySelectorAll('.skill-chip.on'))
    .map((chip) => chip.textContent.replace(/[^\w\s]/g, '').trim())
    .filter(Boolean);
}

function collectPayload() {
  const bioInput = document.querySelector('#bioF textarea');
  const bioView = document.querySelector('#bioV .bio-text');
  const rateInputs = document.querySelectorAll('.rate-input');

  const rateMinRaw = rateInputs[0]?.value?.trim() || '';
  const rateMaxRaw = rateInputs[1]?.value?.trim() || '';

  return {
    bio: (bioInput?.value?.trim() || bioView?.textContent?.trim() || null),
    rate_min: rateMinRaw ? Number(rateMinRaw) : null,
    rate_max: rateMaxRaw ? Number(rateMaxRaw) : null,
    skills: collectSkills(),
    is_available: !!document.querySelector('.toggle-switch input')?.checked,
  };
}

async function saveProfile() {
  try {
    const payload = collectPayload();
    const updated = await apiRequest('/v1/profiles/me', {
      method: 'PATCH',
      body: payload,
    });
    applyProfile(updated?.profile, updated?.fundi_profile);
    alert('Profile changes saved.');
  } catch (error) {
    alert(error.message || 'Failed to save profile changes.');
  }
}

function mountSaveButton() {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Save Changes';
  button.style.cssText = `
    position: fixed;
    right: 1rem;
    bottom: 5.5rem;
    z-index: 999;
    padding: 0.8rem 1.2rem;
    border: none;
    border-radius: 4px;
    background: var(--ink);
    color: #F5F0E8;
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 8px 20px rgba(0,0,0,0.25);
  `;
  button.addEventListener('click', saveProfile);
  document.body.appendChild(button);
}

window.toggleInline = (fieldId) => {
  const field = document.getElementById(fieldId);
  if (!field) return;
  field.style.display = field.style.display === 'none' ? 'block' : 'none';
};

async function bootstrap() {
  const data = await apiRequest('/v1/profiles/me');
  applyProfile(data?.profile, data?.fundi_profile);
  mountSaveButton();
}

bootstrap().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Worker profile edit failed to initialize:', error.message);
});
