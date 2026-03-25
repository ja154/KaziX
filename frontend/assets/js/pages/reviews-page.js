import { apiRequest, escapeHtml, formatTimeAgo } from '../api/client.js';
import { requireAuth } from '../auth/session.js';

const state = {
  currentUserId: null,
  pending: null,
  mainRating: 0,
  subRatings: {
    quality: 0,
    punctuality: 0,
    communication: 0,
    value_for_money: 0,
  },
};

function stars(value) {
  const count = Math.max(0, Math.min(5, Number(value || 0)));
  return `${'★'.repeat(count)}${'☆'.repeat(5 - count)}`;
}

function setTabCount(tabIndex, count) {
  const tab = document.querySelectorAll('.rtab')[tabIndex];
  if (!tab) return;
  const badge = tab.querySelector('.tc');
  if (badge) badge.textContent = String(count);
}

function renderSummary(summary) {
  const avgEl = document.querySelector('.rep-score-big');
  const totalEl = document.querySelector('.rep-total');
  const starsEl = document.querySelector('.rep-stars');
  if (avgEl) avgEl.textContent = Number(summary.average || 0).toFixed(1);
  if (totalEl) totalEl.textContent = `${summary.count} reviews`;
  if (starsEl) starsEl.textContent = stars(Math.round(summary.average || 0));

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
        No reviews yet.
      </div>
    `;
    return;
  }

  container.innerHTML = rows.map((review) => {
    const reviewer = Array.isArray(review.profiles) ? review.profiles[0] : review.profiles;
    return `
      <div class="rev-card">
        <div class="rc-top">
          <div class="rc-avatar">👤</div>
          <div class="rc-meta">
            <div class="rc-name">${escapeHtml(reviewer?.full_name || 'KaziX user')}</div>
            <div class="rc-trade">About this client</div>
            <div class="rc-job">Booking ${escapeHtml((review.booking_id || '').slice(0, 8).toUpperCase())}</div>
          </div>
          <div class="rc-right">
            <div class="rc-stars">${stars(review.rating)}</div>
            <div class="rc-score">${Number(review.rating || 0).toFixed(1)}</div>
            <div class="rc-date">${formatTimeAgo(review.created_at)}</div>
          </div>
        </div>
        <div class="rc-body">"${escapeHtml(review.comment || '')}"</div>
      </div>
    `;
  }).join('');
}

function renderGivenPlaceholder() {
  const container = document.querySelector('#tab-given');
  if (!container) return;
  container.innerHTML = `
    <div style="text-align:center;padding:2rem;color:var(--muted);font-size:.875rem;background:white;border:1px solid var(--border);border-radius:6px">
      Reviews you've submitted will appear here in a future backend endpoint.
    </div>
  `;
}

function renderPendingSection() {
  const container = document.getElementById('tab-pending');
  if (!container) return;

  if (!state.pending) {
    container.innerHTML = `
      <div style="text-align:center;padding:2rem;color:var(--muted);font-size:.875rem">
        No pending reviews
      </div>
    `;
    setTabCount(2, 0);
    return;
  }

  container.innerHTML = `
    <div class="pending-review-card" onclick="openReviewModal('${escapeHtml(state.pending.name)}', '${escapeHtml(state.pending.emoji)}', '${escapeHtml(state.pending.trade)}', '${escapeHtml(state.pending.job)}', '${escapeHtml(state.pending.booking_id)}')">
      <div class="prc-avatar">${escapeHtml(state.pending.emoji)}</div>
      <div class="prc-info">
        <div class="prc-title">Leave a review for ${escapeHtml(state.pending.name)}</div>
        <div class="prc-sub">${escapeHtml(state.pending.job)} · Booking ${escapeHtml(state.pending.booking_id.slice(0, 8).toUpperCase())}</div>
      </div>
      <button class="prc-btn">⭐ Write Review</button>
    </div>
  `;
  setTabCount(2, 1);
}

window.switchTab = (id, element) => {
  document.querySelectorAll('.rtab').forEach((tab) => tab.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach((content) => content.classList.remove('active'));
  if (element) element.classList.add('active');
  const target = document.getElementById(`tab-${id}`);
  if (target) target.classList.add('active');
};

window.setMainStar = (value) => {
  state.mainRating = Number(value) || 0;
  const starsEl = document.querySelectorAll('#mainStars span');
  starsEl.forEach((starEl, index) => {
    const lit = index < state.mainRating;
    starEl.textContent = lit ? '★' : '☆';
    starEl.classList.toggle('lit', lit);
  });
};

const subKeyMap = {
  sq: 'quality',
  sp: 'punctuality',
  sc: 'communication',
  sv: 'value_for_money',
};

window.setStar = (id, value) => {
  const key = subKeyMap[id];
  if (!key) return;
  state.subRatings[key] = Number(value) || 0;

  const starsEl = document.querySelectorAll(`#${id} .srp-star`);
  starsEl.forEach((starEl, index) => {
    const lit = index < state.subRatings[key];
    starEl.textContent = lit ? '★' : '☆';
    starEl.classList.toggle('lit', lit);
  });
};

window.openReviewModal = (name, emoji, trade, job, bookingId) => {
  const modal = document.getElementById('reviewModal');
  if (!modal) return;

  state.pending = {
    booking_id: bookingId || state.pending?.booking_id || null,
    name: name || state.pending?.name || 'Worker',
    emoji: emoji || state.pending?.emoji || '👷',
    trade: trade || state.pending?.trade || '',
    job: job || state.pending?.job || 'Job',
  };

  document.getElementById('revieweeName').textContent = state.pending.name;
  document.getElementById('revieweeEmoji').textContent = state.pending.emoji;
  document.getElementById('reviewJobName').textContent = state.pending.job;
  modal.classList.add('open');
};

window.closeReviewModal = () => {
  const modal = document.getElementById('reviewModal');
  if (modal) modal.classList.remove('open');
};

window.submitReview = async () => {
  if (!state.pending?.booking_id) {
    alert('Missing booking id. Open this page with ?booking=<booking_id>.');
    return;
  }
  if (state.mainRating < 1) {
    alert('Please select an overall rating.');
    return;
  }

  const commentEl = document.querySelector('.review-textarea');
  const comment = commentEl?.value?.trim() || '';
  if (comment.length < 5) {
    alert('Please write a short review comment.');
    return;
  }

  const wouldHireAgain = !!document.querySelector('.modal input[type="checkbox"]')?.checked;

  try {
    await apiRequest('/v1/reviews', {
      method: 'POST',
      body: {
        booking_id: state.pending.booking_id,
        rating: state.mainRating,
        comment,
        quality: state.subRatings.quality || null,
        punctuality: state.subRatings.punctuality || null,
        communication: state.subRatings.communication || null,
        value_for_money: state.subRatings.value_for_money || null,
        would_hire_again: wouldHireAgain,
      },
    });

    window.closeReviewModal();
    alert('Review submitted successfully.');
    state.pending = null;
    renderPendingSection();
    await loadReceivedReviews();
  } catch (error) {
    alert(error.message || 'Failed to submit review.');
  }
};

async function loadReceivedReviews() {
  const response = await apiRequest(`/v1/reviews/${encodeURIComponent(state.currentUserId)}`);
  const rows = response?.data || [];
  const summary = response?.summary || { count: 0, average: 0, breakdown: {} };
  renderSummary(summary);
  renderReceivedReviews(rows);
  setTabCount(1, summary.count || rows.length);
}

function initPendingFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const bookingId = params.get('booking');
  if (!bookingId) {
    state.pending = null;
    return;
  }

  state.pending = {
    booking_id: bookingId,
    name: params.get('reviewee') || 'Worker',
    emoji: params.get('emoji') || '👷',
    trade: params.get('trade') || '',
    job: params.get('job') || 'Completed booking',
  };
}

async function bootstrap() {
  const session = await requireAuth();
  state.currentUserId = session.user.id;

  initPendingFromQuery();
  renderGivenPlaceholder();
  renderPendingSection();
  await loadReceivedReviews();
}

bootstrap().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Reviews page failed to initialize:', error.message);
});
