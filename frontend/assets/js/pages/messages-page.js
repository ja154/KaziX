import { escapeHtml } from '../api/client.js';
import { listMessages, sendMessage } from '../api/messages.js';
import { requireAuth } from '../auth/session.js';

const state = {
  currentUserId: null,
  conversations: [],
  selectedBookingId: null,
  thread: [],
  profileCache: new Map(),
};

const convListEl = document.querySelector('.conv-items');
const chatMessagesEl = document.getElementById('chatMessages');
const chatNameEl = document.querySelector('.chat-name');
const chatSubEl = document.querySelector('.chat-sub');
const chatAvatarEl = document.querySelector('.chat-header-avatar');
const profileLinkEl = document.querySelector('.chat-actions a');

function shortId(value) {
  if (!value) return 'Unknown';
  return `${value.slice(0, 8)}...`;
}

function formatTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  return date.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' });
}

async function fetchPublicProfile(userId) {
  if (!userId) return null;
  if (state.profileCache.has(userId)) return state.profileCache.get(userId);

  try {
    const response = await fetch(`/v1/profiles/${encodeURIComponent(userId)}`);
    if (!response.ok) throw new Error('profile fetch failed');
    const profile = await response.json();
    state.profileCache.set(userId, profile);
    return profile;
  } catch {
    const fallback = { id: userId, full_name: shortId(userId), role: 'fundi' };
    state.profileCache.set(userId, fallback);
    return fallback;
  }
}

function mapConversations(rows) {
  const byBooking = new Map();
  for (const msg of rows) {
    const bookingId = msg.booking_id;
    if (!bookingId) continue;
    const partnerId = msg.sender_id === state.currentUserId ? msg.recipient_id : msg.sender_id;

    if (!byBooking.has(bookingId)) {
      byBooking.set(bookingId, {
        bookingId,
        partnerId,
        lastMessage: msg,
        unreadCount: 0,
      });
    }
    const conv = byBooking.get(bookingId);
    const currentLast = new Date(conv.lastMessage.created_at).getTime();
    const candidate = new Date(msg.created_at).getTime();
    if (candidate >= currentLast) conv.lastMessage = msg;
    if (msg.recipient_id === state.currentUserId && !msg.is_read) conv.unreadCount += 1;
  }

  return Array.from(byBooking.values()).sort(
    (a, b) => new Date(b.lastMessage.created_at) - new Date(a.lastMessage.created_at),
  );
}

async function renderConversations() {
  if (!convListEl) return;

  if (state.conversations.length === 0) {
    convListEl.innerHTML = `
      <div class="conv-item">
        <div class="ci-avatar">💬</div>
        <div class="ci-info">
          <div class="ci-name">No conversations yet</div>
          <div class="ci-preview">Messages will appear here once you chat on a booking.</div>
        </div>
      </div>
    `;
    return;
  }

  await Promise.all(state.conversations.map((c) => fetchPublicProfile(c.partnerId)));

  convListEl.innerHTML = state.conversations.map((conv) => {
    const profile = state.profileCache.get(conv.partnerId) || {};
    const isActive = conv.bookingId === state.selectedBookingId;
    const unreadClass = conv.unreadCount > 0 ? ' unread' : '';
    const activeClass = isActive ? ' active' : '';

    return `
      <div class="conv-item${unreadClass}${activeClass}" onclick="selectConv('${escapeHtml(conv.bookingId)}')">
        <div class="ci-avatar">💬</div>
        <div class="ci-info">
          <div class="ci-name">
            ${escapeHtml(profile.full_name || shortId(conv.partnerId))}
            <span class="ci-time">${formatTime(conv.lastMessage.created_at)}</span>
          </div>
          <div class="ci-job">Booking · ${escapeHtml(conv.bookingId.slice(0, 8).toUpperCase())}</div>
          <div class="ci-preview">${escapeHtml(conv.lastMessage.body || '')}</div>
        </div>
        ${conv.unreadCount > 0 ? `<div class="ci-unread-badge">${conv.unreadCount}</div>` : ''}
      </div>
    `;
  }).join('');
}

function renderThread() {
  if (!chatMessagesEl) return;

  if (state.thread.length === 0) {
    chatMessagesEl.innerHTML = `
      <div class="sys-msg">
        No messages yet for this booking. Start the conversation below.
      </div>
    `;
    return;
  }

  chatMessagesEl.innerHTML = state.thread.map((msg) => {
    const outgoing = msg.sender_id === state.currentUserId;
    return `
      <div class="msg-bubble${outgoing ? ' outgoing' : ''}">
        <div class="bubble-avatar">${outgoing ? '🏠' : '🔧'}</div>
        <div>
          <div class="bubble-content">${escapeHtml(msg.body || '')}</div>
          <div class="bubble-time">${formatTime(msg.created_at)}</div>
        </div>
      </div>
    `;
  }).join('');

  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function getSelectedConversation() {
  return state.conversations.find((c) => c.bookingId === state.selectedBookingId) || null;
}

function updateHeader() {
  const selected = getSelectedConversation();
  if (!selected) {
    if (chatNameEl) chatNameEl.textContent = 'Select a conversation';
    if (chatSubEl) chatSubEl.textContent = 'Choose a booking thread to view messages';
    if (chatAvatarEl) chatAvatarEl.innerHTML = '💬';
    return;
  }

  const profile = state.profileCache.get(selected.partnerId) || {};
  if (chatNameEl) chatNameEl.textContent = profile.full_name || shortId(selected.partnerId);
  if (chatSubEl) {
    chatSubEl.textContent = `Booking ${selected.bookingId.slice(0, 8).toUpperCase()}`;
  }
  if (chatAvatarEl) {
    chatAvatarEl.innerHTML = '💬<div class="chat-online"></div>';
  }
  if (profileLinkEl) {
    profileLinkEl.href = `worker-profile.html?user=${encodeURIComponent(selected.partnerId)}`;
  }
}

async function loadThread(bookingId) {
  const response = await listMessages({ booking_id: bookingId, limit: 200 });
  state.thread = response?.data || [];
  state.selectedBookingId = bookingId;

  const selected = getSelectedConversation();
  if (selected) selected.unreadCount = 0;

  await renderConversations();
  updateHeader();
  renderThread();
}

async function loadConversations() {
  const response = await listMessages({ limit: 200 });
  const rows = response?.data || [];
  state.conversations = mapConversations(rows);

  const urlBooking = new URLSearchParams(window.location.search).get('booking');
  state.selectedBookingId = urlBooking || state.conversations[0]?.bookingId || null;

  await renderConversations();
  updateHeader();

  if (state.selectedBookingId) {
    try {
      await loadThread(state.selectedBookingId);
    } catch {
      state.selectedBookingId = state.conversations[0]?.bookingId || null;
      if (state.selectedBookingId) {
        await loadThread(state.selectedBookingId);
      } else {
        renderThread();
      }
    }
  } else {
    renderThread();
  }
}

window.selectConv = async (bookingId) => {
  if (!bookingId) return;
  try {
    await loadThread(bookingId);
  } catch (error) {
    // eslint-disable-next-line no-console
    console.error('Failed to load thread:', error.message);
  }
};

window.sendMessage = async () => {
  const input = document.getElementById('msgInput');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  const selected = getSelectedConversation();
  if (!selected) {
    alert('Select a conversation first.');
    return;
  }

  try {
    const created = await sendMessage({
      booking_id: selected.bookingId,
      recipient_id: selected.partnerId,
      body: text,
    });
    input.value = '';

    state.thread.push(created);
    selected.lastMessage = created;

    state.conversations = state.conversations.sort(
      (a, b) => new Date(b.lastMessage.created_at) - new Date(a.lastMessage.created_at),
    );

    await renderConversations();
    renderThread();
  } catch (error) {
    alert(error.message || 'Failed to send message.');
  }
};

window.handleKey = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    window.sendMessage();
  }
};

async function bootstrap() {
  const session = await requireAuth();
  state.currentUserId = session.user.id;
  await loadConversations();
}

bootstrap().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Messages page failed to initialize:', error.message);
});
