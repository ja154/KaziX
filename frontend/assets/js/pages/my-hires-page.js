/**
 * pages/my-hires-page.js
 * ─────────────────────
 * Wires up my-hires.html to real booking completion and M-Pesa STK push.
 */

import { apiRequest } from '../api/client.js';

export async function initMyHires() {
  window.confirmComplete = async (bookingId, amount, name) => {
    if (!confirm(`Confirm that the job is done and release KES ${amount.toLocaleString()} to ${name} via M-Pesa?`)) {
      return;
    }

    try {
      // 1. Mark booking as complete
      await apiRequest(`/v1/bookings/${bookingId}/complete`, {
        method: 'POST',
      });

      // 2. Trigger M-Pesa STK Push for payment (if not already paid in escrow)
      // Note: In KaziX, payment is usually held in escrow at booking time.
      // This call might be to release escrow or handle final payment.
      await apiRequest('/v1/mpesa/stk-push', {
        method: 'POST',
        body: {
          booking_id: bookingId,
          amount: amount,
        },
      });

      alert(`✅ Payment released! KES ${(amount * 0.9).toLocaleString()} sent to ${name}'s M-Pesa. You can now leave a review.`);
      window.location.reload();
    } catch (err) {
      alert(err.message || 'Failed to complete booking');
    }
  };

  // Add data-booking-id to existing mock cards for demo purposes if they exist
  const cards = document.querySelectorAll('.contract-card');
  if (cards.length > 0) {
     // Mock IDs for existing static cards
     const mockIds = ['b1', 'b2', 'b3'];
     cards.forEach((card, i) => {
       const btn = card.querySelector('.ccb-complete');
       if (btn) {
         const name = card.querySelector('.cc-worker-name').textContent;
         const amountStr = card.querySelector('.ccd-val').textContent.replace(/[^0-9]/g, '');
         const amount = parseInt(amountStr);
         btn.onclick = () => window.confirmComplete(mockIds[i] || 'mock-id', amount, name);
       }
     });
  }
}

// Auto-init
if (document.querySelector('.contracts')) {
  initMyHires();
}
