import { apiRequest, escapeHtml, formatTimeAgo } from '../api/client.js';

const state = {
  notifications: [],
  filter: 'all',
};

const typeToCategory = {
  new_application: 'applications',
  hired: 'jobs',
  payment: 'payments',
  message: 'messages',
};

function iconForType(type) {
  switch (type) {
    case 'new_application':
      return '👥';
    case 'message':
      return '💬';
    case 'payment':
      return '💳';
    case 'dispute':
      return '⚖️';
    case 'review':
    case 'review_request':
      return '⭐';
    case 'kyc_update':
      return '🪪';
    default:
      return '🔔';
  }
}

function bubbleClassForType(type) {
  switch (type) {
    case 'payment':
      return 'nib-green';
    case 'message':
      return 'nib-ink';
    case 'dispute':
      return 'nib-rust';
    default:
      return 'nib-saffron';
  }
}

function matchesFilter(notification, filter) {
  if (filter === 'all') return true;
  return (typeToCategory[notification.type] || 'jobs') === filter;
}

function groupLabelForDate(iso) {
  const date = new Date(iso);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startMsg = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.floor((startToday - startMsg) / 86400000);
  if (diffDays <= 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays <= 7) return 'Earlier This Week';
  return date.toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
}

function updateBadges() {
  const unread = state.notifications.filter((n) => !n.is_read).length;

  const topDot = document.querySelector('.notif-dot');
  if (topDot) {
    if (unread > 0) {
      topDot.style.display = 'flex';
      topDot.textContent = unread > 9 ? '9+' : String(unread);
      topDot.dataset.count = String(unread);
    } else {
      topDot.style.display = 'none';
      topDot.textContent = '';
      topDot.dataset.count = '0';
    }
  }

  const sidebarBadge = document.querySelector('a.nav-item[href="notifications.html"] .ni-badge');
  if (sidebarBadge) sidebarBadge.textContent = String(unread);
}

function render() {
  const list = document.getElementById('notifList');
  const empty = document.getElementById('emptyState');
  if (!list) return;

  const rows = state.notifications.filter((n) => matchesFilter(n, state.filter));
  if (rows.length === 0) {
    list.innerHTML = '';
    if (empty) empty.style.display = 'block';
    updateBadges();
    return;
  }
  if (empty) empty.style.display = 'none';

  const parts = [];
  let lastLabel = '';
  rows.forEach((n) => {
    const label = groupLabelForDate(n.created_at);
    if (label !== lastLabel) {
      parts.push(`<div class="group-label">${escapeHtml(label)}</div>`);
      lastLabel = label;
    }

    const unreadClass = n.is_read ? '' : ' unread';
    const action = n.action_url
      ? `<a href="${escapeHtml(n.action_url)}" class="nia-btn nia-primary">Open</a>`
      : '';

    parts.push(`
      <div class="notif-item${unreadClass}" data-id="${escapeHtml(n.id)}" data-url="${escapeHtml(n.action_url || '')}" data-type="${escapeHtml(typeToCategory[n.type] || 'jobs')}" onclick="openNotification(event)">
        <div class="ni-bubble ${bubbleClassForType(n.type)}">${iconForType(n.type)}</div>
        <div class="ni-content">
          <div class="ni-title">${escapeHtml(n.title)}</div>
          <div class="ni-sub">${escapeHtml(n.body)}</div>
          <div class="ni-time">${formatTimeAgo(n.created_at)}</div>
          <div class="ni-actions">${action}</div>
        </div>
        ${n.is_read ? '' : '<div class="unread-indicator"></div>'}
        <button class="dismiss-btn" onclick="dismiss(event)" title="Dismiss">✕</button>
      </div>
    `);
  });

  list.innerHTML = parts.join('');
  updateBadges();
}

async function loadNotifications() {
  const data = await apiRequest('/v1/notifications?limit=200');
  state.notifications = (data?.data || []).slice();
  render();
}

window.filterNotifs = (filter, buttonEl) => {
  state.filter = filter;
  document.querySelectorAll('.nf-btn').forEach((btn) => btn.classList.remove('active'));
  if (buttonEl) buttonEl.classList.add('active');
  render();
};

window.dismiss = (eventOrButton) => {
  let btn = eventOrButton?.target || eventOrButton;
  if (btn && btn.tagName !== 'BUTTON') {
    btn = btn.closest('button');
  }
  if (!btn) return;
  if (eventOrButton?.preventDefault) eventOrButton.preventDefault();
  if (eventOrButton?.stopPropagation) eventOrButton.stopPropagation();

  const card = btn.closest('.notif-item');
  const notificationId = card?.dataset?.id;
  if (card) card.remove();
  if (notificationId) {
    state.notifications = state.notifications.filter((n) => n.id !== notificationId);
    updateBadges();
  }
};

window.openNotification = async (eventOrElement) => {
  const target = eventOrElement?.currentTarget || eventOrElement?.target || eventOrElement;
  const card = target?.closest ? target.closest('.notif-item') : null;
  if (!card) return;

  const notificationId = card.dataset.id;
  const actionUrl = card.dataset.url || '';

  try {
    await apiRequest(`/v1/notifications/${notificationId}/read`, { method: 'PATCH' });
    const item = state.notifications.find((n) => n.id === notificationId);
    if (item) item.is_read = true;
    updateBadges();
  } catch {
    // No-op: opening link should still continue even if mark-read fails.
  }

  if (actionUrl) {
    window.location.href = actionUrl;
  }
};

window.markAllRead = async () => {
  const unread = state.notifications.filter((n) => !n.is_read).map((n) => n.id);
  if (unread.length === 0) return;

  await Promise.allSettled(
    unread.map((id) => apiRequest(`/v1/notifications/${id}/read`, { method: 'PATCH' })),
  );
  state.notifications = state.notifications.map((n) => ({ ...n, is_read: true }));
  render();
};

loadNotifications().catch((err) => {
  // Keep static fallback visible if API load fails.
  // eslint-disable-next-line no-console
  console.error('Failed to load notifications:', err.message);
});
