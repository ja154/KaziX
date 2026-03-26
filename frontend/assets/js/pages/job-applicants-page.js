/**
 * pages/job-applicants-page.js
 * ───────────────────────────
 * Wires up job-applicants.html to real applicants and hire flow.
 */

import { apiRequest } from '../api/client.js';

let currentJobId = new URLSearchParams(window.location.search).get('job');
let selectedApplicationId = null;

export async function initJobApplicants() {
  if (currentJobId) {
    await loadApplicants();
  }

  window.openHireModal = (name, amount, appId) => {
    document.getElementById('hiree').textContent = name;
    document.getElementById('hireAmount').value = amount.toString().replace(',', '');
    selectedApplicationId = appId;
    document.getElementById('hireModal').classList.add('open');
  };

  window.closeHireModal = () => {
    document.getElementById('hireModal').classList.remove('open');
  };

  window.rejectApplication = async (appId) => {
    if (!confirm('Are you sure you want to decline this application?')) return;
    try {
      await apiRequest(`/v1/applications/${appId}/reject`, { method: 'POST' });
      loadApplicants();
    } catch (err) {
      alert(err.message || 'Failed to reject application');
    }
  };

  window.confirmHire = async () => {
    const amount = document.getElementById('hireAmount').value;
    const startDate = document.querySelector('#hireModal input[type="date"]').value;

    const confirmBtn = document.querySelector('.modal-confirm');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';

    try {
      await apiRequest('/v1/bookings/hire', {
        method: 'POST',
        body: {
          application_id: selectedApplicationId,
          agreed_amount: parseInt(amount),
          start_date: startDate || undefined,
        },
      });

      window.location.href = 'my-hires.html';
    } catch (err) {
      alert(err.message || 'Failed to hire worker');
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Confirm & Pay via M-Pesa →';
    }
  };
}

async function loadApplicants() {
  try {
    const applicants = await apiRequest(`/v1/jobs/${currentJobId}/applications`);
    renderApplicants(applicants);
  } catch (err) {
    console.error('Failed to load applicants:', err);
  }
}

function renderApplicants(applicants) {
  const container = document.querySelector('.applicants-list');
  if (!container) return;

  if (applicants.length === 0) {
    container.innerHTML = '<div class="empty-state">No applications yet.</div>';
    return;
  }

  container.innerHTML = applicants.map(app => `
    <div class="applicant-card ${app.is_shortlisted ? 'shortlisted' : ''}">
      <div class="ac-top">
        <div class="ac-avatar">${app.worker.avatar || '👤'}${app.worker.is_verified ? '<div class="ac-verified">✓</div>' : ''}</div>
        <div class="ac-info">
          <div class="ac-name">${app.worker.full_name} ${app.is_new ? '<span class="new-badge">New</span>' : ''}</div>
          <div class="ac-trade">${app.worker.trade}</div>
          <div class="ac-loc">📍 ${app.worker.area || app.worker.county}</div>
          <div class="ac-rating"><span class="ac-stars">★★★★★</span><span class="ac-score">${app.worker.rating || '0.0'}</span><span class="ac-jobs">(${app.worker.jobs_completed || 0} jobs)</span></div>
        </div>
        <div class="ac-right">
          <div class="ac-bid">KES ${app.proposed_rate.toLocaleString()}</div>
          <div class="ac-bid-label">Proposed rate</div>
        </div>
      </div>
      <div class="ac-stats">
        <div class="acs"><div class="acs-val">${app.worker.jobs_completed || 0}</div><div class="acs-label">Jobs done</div></div>
        <div class="acs"><div class="acs-val">${app.worker.rating || '0.0'}★</div><div class="acs-label">Rating</div></div>
        <div class="acs"><div class="acs-val">${app.worker.completion_rate || '100'}%</div><div class="acs-label">Completion</div></div>
        <div class="acs"><div class="acs-val">${app.worker.response_time || '< 1hr'}</div><div class="acs-label">Response</div></div>
        <div class="acs"><div class="acs-val">${app.worker.experience_years || 0} yrs</div><div class="acs-label">Experience</div></div>
      </div>
      <div class="ac-cover">"${app.cover_letter || 'No cover letter provided.'}"</div>
      <div class="ac-actions">
        <button class="ac-btn ac-btn-hire" onclick="openHireModal('${app.worker.full_name}', ${app.proposed_rate}, '${app.id}')">✅ Hire ${app.worker.full_name.split(' ')[0]} — KES ${app.proposed_rate.toLocaleString()}</button>
        <a href="messages.html?worker=${app.worker_id}" class="ac-btn ac-btn-msg">💬 Message</a>
        <a href="worker-profile.html?id=${app.worker_id}" class="ac-btn ac-btn-view">View Profile</a>
        <button class="ac-btn ac-btn-reject" onclick="rejectApplication('${app.id}')">Decline ✕</button>
      </div>
    </div>
  `).join('');
}


// Auto-init
initJobApplicants();
