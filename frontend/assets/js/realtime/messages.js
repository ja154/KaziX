/**
 * realtime/messages.js
 * ─────────────────────
 * Task 7 — Real-time message subscriptions.
 *
 * Import on messages.html. Subscribes to INSERT events on the messages
 * table filtered to the current user as recipient.
 *
 * Usage:
 *   import { subscribeToMessages, unsubscribeMessages } from './realtime/messages.js';
 *   const unsub = subscribeToMessages(supabaseClient, currentUserId, onNewMessage);
 *   window.addEventListener('beforeunload', unsub);
 */

/**
 * @param {import('@supabase/supabase-js').SupabaseClient} supabase
 * @param {string} currentUserId
 * @param {(message: object) => void} onMessage  - called with each new message row
 * @returns {() => void} cleanup function — call on page unload
 */
export function subscribeToMessages(supabase, currentUserId, onMessage) {
  const channel = supabase
    .channel(`messages:recipient:${currentUserId}`)
    .on(
      'postgres_changes',
      {
        event:  'INSERT',
        schema: 'public',
        table:  'messages',
        filter: `recipient_id=eq.${currentUserId}`,
      },
      (payload) => {
        const msg = payload.new;
        appendMessageBubble(msg);
        onMessage(msg);
      }
    )
    .subscribe((status) => {
      if (status === 'SUBSCRIBED') {
        console.debug('[KaziX] Messages channel subscribed');
      }
    });

  return () => {
    supabase.removeChannel(channel);
    console.debug('[KaziX] Messages channel unsubscribed');
  };
}

/**
 * Appends a received message bubble to .chat-messages
 * and scrolls to bottom — matches the existing bubble HTML in messages.html.
 *
 * @param {object} msg - message row from Supabase
 */
function appendMessageBubble(msg) {
  const container = document.querySelector('.chat-messages');
  if (!container) return;

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.style.animation = 'slideUp 0.3s ease both';
  bubble.innerHTML = `
    <div class="bubble-avatar">🔧</div>
    <div>
      <div class="bubble-content">${escapeHtml(msg.body)}</div>
      <div class="bubble-time">${formatTime(msg.created_at)}</div>
    </div>
  `;

  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}

function formatTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' });
}
