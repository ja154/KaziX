/**
 * api/reviews.js
 * ──────────────
 * API client for review submission and listing.
 */

import { apiRequest } from './client.js';

/**
 * Submits a new review for a completed booking.
 * @param {object} payload - { booking_id, rating, comment, quality, ... }
 */
export async function submitReview(payload) {
  return apiRequest('/v1/reviews', {
    method: 'POST',
    body: payload,
  });
}

/**
 * Fetches the public review listing and summary for a user.
 * @param {string} userId
 * @returns {Promise<{ data: Array, summary: object }>}
 */
export async function listUserReviews(userId) {
  return apiRequest(`/v1/reviews/${encodeURIComponent(userId)}`, {
    requireSession: false,
  });
}
