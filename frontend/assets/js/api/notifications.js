/**
 * api/notifications.js
 * ────────────────────
 * API client for user notification inbox.
 */

import { apiRequest } from './client.js';

/**
 * Returns notifications for the authenticated user.
 * @param {object} params - { limit, offset, unread_only }
 */
export async function listNotifications(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.append('limit', params.limit);
  if (params.offset) query.append('offset', params.offset);
  if (params.unread_only !== undefined) query.append('unread_only', params.unread_only);

  const queryString = query.toString();
  const path = `/v1/notifications${queryString ? `?${queryString}` : ''}`;

  return apiRequest(path);
}

/**
 * Marks one notification as read.
 * @param {string} notificationId
 */
export async function markNotificationRead(notificationId) {
  return apiRequest(`/v1/notifications/${notificationId}/read`, {
    method: 'PATCH',
  });
}
