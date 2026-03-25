/**
 * api/messages.js
 * ───────────────
 * API client for in-app chat.
 */

import { apiRequest } from './client.js';

/**
 * Lists chat messages for the current user.
 * @param {object} params - { booking_id, limit, offset }
 */
export async function listMessages(params = {}) {
  const query = new URLSearchParams();
  if (params.booking_id) query.append('booking_id', params.booking_id);
  if (params.limit) query.append('limit', params.limit);
  if (params.offset) query.append('offset', params.offset);

  const queryString = query.toString();
  const path = `/v1/messages${queryString ? `?${queryString}` : ''}`;

  return apiRequest(path);
}

/**
 * Sends a chat message.
 * @param {object} payload - { booking_id, recipient_id, body }
 */
export async function sendMessage(payload) {
  return apiRequest('/v1/messages', {
    method: 'POST',
    body: payload,
  });
}
