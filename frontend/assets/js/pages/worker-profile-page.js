import { apiRequest, escapeHtml, formatTimeAgo } from '../api/client.js';

function stars(value) {
  const count = Math.max(0, Math.min(5, Math.round(Number(value || 0))));
  return `${'★'.repeat(count)}${'☆'.repeat(5 - count)}`;
}

function setText(selector, value) {
  const node = document.querySelector(selector);
  if (node && value !== undefined && value !== null) node.textContent = value;
}

function applyProfile(profile) {
  const fundi = profile?.fundi_profile || {};
  const name = profile?.full_name || 'Worker';
  const trade = fundi.trade || 'Fundi';

  document.title = `${name} — ${trade} · KaziX`;
  setText('.profile-name', name);
  setText('.profile-trade', trade);

  const location = [profile?.area, profile?.county].filter(Boolean).join(', ');
  setText('.profile-location', `📍 ${location || 'Kenya'} · Member on KaziX`);

  setText('.profile-stat:nth-child(1) .ps-value', String(fundi.jobs_completed || 0));
  setText('.profile-stat:nth-child(2) .ps-value', `${Number(fundi.rating_avg || 0).toFixed(1)}★`);
  setText('.profile-stat:nth-child(3) .ps-value', `${fundi.experience_years || 0} yrs`);

  const responseRate = profile?.is_verified ? '98%' : '—';
  setText('.profile-stat:nth-child(4) .ps-value', responseRate);

  if (fundi.bio) {
    const bioLines = document.querySelectorAll('.card .bio-text');
    if (bioLines[0]) bioLines[0].textContent = fundi.bio;
    for (let i = 1; i < bioLines.length; i += 1) {
      bioLines[i].style.display = 'none';
    }
  }

  if (Array.isArray(fundi.skills) && fundi.skills.length) {
    const wrap = document.querySelector('.skills-wrap');
    if (wrap) {
      wrap.innerHTML = fundi.skills
        .map((skill) => `<span class="skill-pill">${escapeHtml(skill)}</span>`)
        .join('');
    }
  }

  const rateDisplay = document.querySelector('.rate-display');
  const rateRange = document.querySelector('.rate-range');
  if (rateDisplay) {
    const min = Number(fundi.rate_min || 0);
    const max = Number(fundi.rate_max || 0);
    const shown = min > 0 ? min : max;
    rateDisplay.innerHTML = `KES ${shown.toLocaleString()}<span>/hr</span>`;
  }
  if (rateRange) {
    const min = Number(fundi.rate_min || 0);
    const max = Number(fundi.rate_max || 0);
    if (min || max) {
      rateRange.textContent = `Range: KES ${min.toLocaleString()} – ${max.toLocaleString()}/hr · Negotiable`;
    }
  }
}

function applyReviews(reviews, summary) {
  const title = Array.from(document.querySelectorAll('.card-title')).find((el) =>
    el.textContent.trim().startsWith('Reviews'),
  );
  if (title) title.textContent = `Reviews (${summary.count || reviews.length})`;

  setText('.big-rating', Number(summary.average || 0).toFixed(1));
  setText('.rating-stars-big', stars(summary.average || 0));

  const bars = document.querySelectorAll('.rating-bar-row');
  bars.forEach((bar) => {
    const labelText = bar.querySelector('.bar-label')?.textContent?.replace('★', '') || '0';
    const star = Number(labelText);
    if (!star) return;
    const value = Number(summary.breakdown?.[String(star)] || 0);
    const pct = summary.count ? Math.round((value / summary.count) * 100) : 0;
    const fill = bar.querySelector('.bar-fill');
    const pctText = bar.querySelector('.bar-pct');
    if (fill) fill.style.width = `${pct}%`;
    if (pctText) pctText.textContent = `${pct}%`;
  });

  const card = title?.closest('.card');
  if (!card) return;

  const existingItems = card.querySelectorAll('.review-item');
  existingItems.forEach((item) => item.remove());

  const button = card.querySelector('button');
  if (button) button.remove();

  const items = reviews.slice(0, 6).map((review) => {
    const reviewer = Array.isArray(review.profiles) ? review.profiles[0] : review.profiles;
    const wrapper = document.createElement('div');
    wrapper.className = 'review-item';
    wrapper.innerHTML = `
      <div class="review-header">
        <div>
          <div class="reviewer-name">${escapeHtml(reviewer?.full_name || 'KaziX user')}</div>
          <div class="review-date">${escapeHtml(formatTimeAgo(review.created_at))}</div>
        </div>
      </div>
      <div class="review-stars">${stars(review.rating)}</div>
      <div class="review-text">${escapeHtml(review.comment || '')}</div>
      <div class="review-job">Booking: ${escapeHtml((review.booking_id || '').slice(0, 8).toUpperCase())}</div>
    `;
    return wrapper;
  });
  items.forEach((node) => card.appendChild(node));
}

async function bootstrap() {
  const params = new URLSearchParams(window.location.search);
  const userId = params.get('user');
  if (!userId) return; // keep static content fallback

  const profileResponse = await fetch(`/v1/profiles/${encodeURIComponent(userId)}`);
  if (!profileResponse.ok) throw new Error('Failed to load profile');
  const profile = await profileResponse.json();
  applyProfile(profile);

  const reviewsResponse = await apiRequest(`/v1/reviews/${encodeURIComponent(userId)}`, {
    requireSession: false,
  });
  applyReviews(reviewsResponse?.data || [], reviewsResponse?.summary || {});
}

bootstrap().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Worker profile page failed to initialize:', error.message);
});
