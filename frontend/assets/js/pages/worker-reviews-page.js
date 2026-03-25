import { escapeHtml, formatTimeAgo } from '../api/client.js';
import { listUserReviews } from '../api/reviews.js';
import { requireAuth } from '../auth/session.js';

const state = {
  currentUserId: null,
};

function stars(value) {
  const count = Math.max(0, Math.min(5, Math.round(Number(value || 0))));
  return `${'★'.repeat(count)}${'☆'.repeat(5 - count)}`;
}

function setTabCount(tabIndex, count) {
  const tab = document.querySelectorAll('.tab')[tabIndex];
  if (!tab) return;
  const badge = tab.querySelector('.tc');
  if (badge) badge.textContent = String(count);
}

function renderSummary(summary) {
  const scoreEl = document.querySelector('.rep-score');
  const countEl = document.querySelector('.rep-count');
  const starsEl = document.querySelector('.rep-stars');

  if (scoreEl) scoreEl.textContent = Number(summary.average || 0).toFixed(1);
  if (countEl) countEl.textContent = `${summary.count} reviews as a fundi`;
  if (starsEl) starsEl.textContent = stars(summary.average || 0);

  const rows = Array.from(document.querySelectorAll('.rb-row'));
  rows.forEach((row) => {
    const label = row.querySelector('.rb-label')?.textContent?.trim()?.replace('★', '');
    const star = Number(label);
    if (!star) return;
    const value = Number(summary.breakdown?.[String(star)] || 0);
    const pct = summary.count > 0 ? Math.round((value / summary.count) * 100) : 0;
    const fill = row.querySelector('.rb-fill');
    const pctEl = row.querySelector('.rb-pct');
    if (fill) fill.style.width = `${pct}%`;
    if (pctEl) pctEl.textContent = `${pct}%`;
  });
}

function renderReceivedReviews(rows) {
  const container = document.querySelector('#tab-received .reviews-list');
  if (!container) return;

  if (!rows.length) {
    container.innerHTML = `
      <div style="text-align:center;padding:2rem;color:var(--muted);font-size:.875rem">
        You haven't received any reviews yet.
      </div>
    `;
    return;
  }

  container.innerHTML = rows.map((review) => {
    const reviewer = Array.isArray(review.profiles) ? review.profiles[0] : review.profiles;
    return `
      <div class="rev-card">
        <div class="rc-top">
          <div class="rc-avatar">🏠</div>
          <div style="flex:1">
            <div class="rc-name">${escapeHtml(reviewer?.full_name || 'KaziX Client')}</div>
            <div class="rc-job">Booking ${escapeHtml((review.booking_id || '').slice(0, 8).toUpperCase())}</div>
          </div>
          <div class="rc-right">
            <div class="rc-stars">${stars(review.rating)}</div>
            <div class="rc-score">${Number(review.rating || 0).toFixed(1)}</div>
            <div class="rc-date">${formatTimeAgo(review.created_at)}</div>
          </div>
        </div>
        <div class="rc-body">"${escapeHtml(review.comment || '')}"</div>
        <div class="sub-ratings">
          <div><div class="sr-label">Quality</div><div class="sr-stars">${stars(review.quality)}</div></div>
          <div><div class="sr-label">Punctuality</div><div class="sr-stars">${stars(review.punctuality)}</div></div>
          <div><div class="sr-label">Communication</div><div class="sr-stars">${stars(review.communication)}</div></div>
          <div><div class="sr-label">Value</div><div class="sr-stars">${stars(review.value_for_money)}</div></div>
        </div>
        ${review.would_hire_again ? '<span class="rehire-badge">🔁 Would hire again</span>' : ''}
      </div>
    `;
  }).join('');
}

function renderGivenPlaceholder() {
  const container = document.querySelector('#tab-given .reviews-list');
  if (!container) return;
  container.innerHTML = `
    <div style="text-align:center;padding:2rem;color:var(--muted);font-size:.875rem">
      Reviews you've left for clients will appear here soon.
    </div>
  `;
}

window.switchTab = (id, el) => {
  document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach((t) => t.classList.remove('active'));
  if (el) el.classList.add('active');
  const target = document.getElementById(`tab-${id}`);
  if (target) target.classList.add('active');
};

async function loadReviews() {
  try {
    const response = await listUserReviews(state.currentUserId);
    const rows = response?.data || [];
    const summary = response?.summary || { count: 0, average: 0, breakdown: {} };
    renderSummary(summary);
    renderReceivedReviews(rows);
    setTabCount(0, summary.count || rows.length);
  } catch (error) {
    // eslint-disable-next-line no-console
    console.error('Failed to load reviews:', error.message);
  }
}

async function bootstrap() {
  const session = await requireAuth();
  state.currentUserId = session.user.id;

  renderGivenPlaceholder();
  await loadReviews();
}

bootstrap().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Worker reviews page failed to initialize:', error.message);
});
