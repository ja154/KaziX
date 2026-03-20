/**
 * realtime/notifications.js
 * ──────────────────────────
 * Task 7 — Real-time notification bell updates.
 *
 * Import in the shared topnav so it runs on every authenticated page.
 * Subscribes to INSERT events on notifications filtered to current user.
 *
 * Usage:
 *   import { subscribeToNotifications } from './realtime/notifications.js';
 *   // Call once after session is loaded:
 *   subscribeToNotifications(supabaseClient, currentUserId);
 */

/**
 * @param {import('@supabase/supabase-js').SupabaseClient} supabase
 * @param {string} currentUserId
 */
export function subscribeToNotifications(supabase, currentUserId) {
  const channel = supabase
    .channel(`notifications:user:${currentUserId}`)
    .on(
      'postgres_changes',
      {
        event:  'INSERT',
        schema: 'public',
        table:  'notifications',
        filter: `user_id=eq.${currentUserId}`,
      },
      (payload) => {
        handleNewNotification(payload.new);
      }
    )
    .subscribe((status) => {
      if (status === 'SUBSCRIBED') {
        console.debug('[KaziX] Notifications channel subscribed');
      }
    });

  // Cleanup on page unload
  window.addEventListener('beforeunload', () => {
    supabase.removeChannel(channel);
  });

  return channel;
}

/**
 * Increments the .notif-dot badge on the topnav bell and shows a toast.
 * Matches the existing topnav HTML structure in styles.css / all dashboard pages.
 *
 * @param {object} notification - notification row from Supabase
 */
function handleNewNotification(notification) {
  // ── 1. Update bell badge count ──────────────────────────
  const dot = document.querySelector('.notif-dot');
  if (dot) {
    const current = parseInt(dot.dataset.count || '0', 10);
    const next    = current + 1;
    dot.dataset.count = next;

    // Show the count as text if > 0
    if (next > 0) {
      dot.textContent = next > 9 ? '9+' : String(next);
      dot.style.display = 'flex';
    }
  }

  // ── 2. Also update the sidebar badge if on notifications page ─
  const sidebarBadge = document.querySelector('.nav-item[href="notifications.html"] .ni-badge');
  if (sidebarBadge) {
    const c = parseInt(sidebarBadge.textContent || '0', 10);
    sidebarBadge.textContent = c + 1;
  }

  // ── 3. Show an in-page toast ─────────────────────────────
  showToast(notification);
}

/**
 * Displays a non-intrusive toast notification at the bottom-right.
 */
function showToast(notification) {
  // Only show toasts if the user isn't already on the notifications page
  if (window.location.pathname.includes('notifications.html')) return;

  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed;
    bottom: 5.5rem;
    right: 1.25rem;
    background: #0D0D0D;
    color: #F5F0E8;
    padding: 0.85rem 1.25rem;
    border-radius: 6px;
    max-width: 320px;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.82rem;
    line-height: 1.5;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    z-index: 9999;
    animation: slideUp 0.3s ease both;
    cursor: pointer;
  `;

  toast.innerHTML = `
    <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:0.85rem;margin-bottom:0.2rem">
      ${escapeHtml(notification.title)}
    </div>
    <div style="color:rgba(245,240,232,0.65)">${escapeHtml(notification.body.slice(0, 100))}</div>
  `;

  // Click → navigate to action_url or notifications page
  toast.addEventListener('click', () => {
    window.location.href = notification.action_url || 'notifications.html';
    toast.remove();
  });

  document.body.appendChild(toast);

  // Auto-dismiss after 5 seconds
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.4s';
    setTimeout(() => toast.remove(), 400);
  }, 5000);
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
