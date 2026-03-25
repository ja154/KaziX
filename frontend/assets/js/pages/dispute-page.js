import { apiRequest, escapeHtml } from '../api/client.js';
import { requireAuth } from '../auth/session.js';

function getBookingIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('booking') || params.get('booking_id') || '';
}

function updateBookingReferenceUI(bookingId) {
  if (!bookingId) return;
  const refValue = document.querySelector('.booking-ref .br-row .br-val');
  if (refValue) refValue.textContent = bookingId;
}

function selectedReasonText() {
  return (
    document.querySelector('.reason-option.selected .ro-label')?.textContent?.trim()
    || 'Other'
  );
}

function descriptionValue() {
  return document.querySelector('textarea.f-input')?.value?.trim() || '';
}

function desiredResolutionValue() {
  return document.querySelector('select.f-input')?.value?.trim() || '';
}

function amountDisputedValue() {
  const raw = document.querySelector('input.f-input[type="number"]')?.value?.trim();
  if (!raw) return null;
  const amount = Number(raw);
  return Number.isFinite(amount) ? amount : null;
}

window.selectReason = (element) => {
  document.querySelectorAll('.reason-option').forEach((option) => option.classList.remove('selected'));
  element.classList.add('selected');
  const input = element.querySelector('input[type="radio"]');
  if (input) input.checked = true;
};

window.submitDispute = async () => {
  const bookingId = getBookingIdFromUrl();
  if (!bookingId) {
    alert('Missing booking id. Open this page with ?booking=<booking_id>.');
    return;
  }

  const description = descriptionValue();
  if (description.length < 20) {
    alert('Please provide more details (at least 20 characters).');
    return;
  }

  if (!confirm('Submit this dispute to KaziX admin? Escrow will be frozen until resolution.')) {
    return;
  }

  try {
    const dispute = await apiRequest('/v1/disputes', {
      method: 'POST',
      body: {
        booking_id: bookingId,
        reason: selectedReasonText(),
        description,
        desired_resolution: desiredResolutionValue() || null,
        amount_disputed: amountDisputedValue(),
        evidence_urls: [],
      },
    });

    const layout = document.querySelector('.dispute-layout');
    if (layout) {
      layout.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:3rem 2rem">
          <div style="font-size:3rem;margin-bottom:1rem">⚖️</div>
          <div style="font-family:'Syne',sans-serif;font-weight:800;font-size:1.75rem;letter-spacing:-.04em;margin-bottom:.75rem">Dispute Submitted</div>
          <div style="color:var(--muted);font-size:.95rem;max-width:480px;margin:0 auto 2rem;line-height:1.7">
            Your dispute has been sent to KaziX admin. We will contact both parties within 24 hours.
          </div>
          <div style="display:inline-flex;flex-direction:column;gap:.5rem;text-align:left;background:var(--cream);border-radius:6px;padding:1.25rem 1.5rem;margin-bottom:2rem;font-size:.82rem">
            <div>📋 Dispute id: <strong>${escapeHtml(dispute.id || '')}</strong></div>
            <div>🧾 Booking id: <strong>${escapeHtml(bookingId)}</strong></div>
            <div>⏱ Response by: <strong>Within 24 hours</strong></div>
          </div>
          <div style="display:flex;gap:1rem;justify-content:center;flex-wrap:wrap">
            <a href="my-hires.html" style="padding:.9rem 2rem;background:var(--ink);color:#F5F0E8;font-family:'Syne',sans-serif;font-weight:700;font-size:.875rem;border-radius:2px;text-decoration:none">Back to My Hires</a>
            <a href="messages.html?booking=${encodeURIComponent(bookingId)}" style="padding:.9rem 2rem;background:transparent;color:var(--ink);font-family:'Syne',sans-serif;font-weight:700;font-size:.875rem;border-radius:2px;text-decoration:none;border:1.5px solid var(--ink)">Open Messages</a>
          </div>
        </div>
      `;
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (error) {
    alert(error.message || 'Failed to submit dispute.');
  }
};

async function bootstrap() {
  await requireAuth();
  updateBookingReferenceUI(getBookingIdFromUrl());
}

bootstrap().catch(() => {
  // Redirect handled by requireAuth.
});
