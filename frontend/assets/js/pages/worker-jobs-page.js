/**
 * pages/worker-jobs-page.js
 * ────────────────────────
 * Wires up worker-jobs.html to real jobs list and application flow.
 */

import { apiRequest, formatTimeAgo } from '../api/client.js';

let selectedJobId = null;

export async function initWorkerJobs() {
  await loadJobs();

  window.openApply = (title, jobId) => {
    document.getElementById('applyJobName').textContent = title;
    selectedJobId = jobId;
    document.getElementById('applyModal').classList.add('open');
  };

  window.submitApply = async () => {
    const bid = document.getElementById('bidInput').value;
    const cover = document.getElementById('coverInput').value;

    if (!bid) {
      alert('Please enter your bid');
      return;
    }

    const submitBtn = document.querySelector('#applyModal .btn-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';

    try {
      await apiRequest('/v1/applications', {
        method: 'POST',
        body: {
          job_id: selectedJobId,
          proposed_rate: parseInt(bid),
          cover_letter: cover,
        },
      });

      document.getElementById('applyModal').classList.remove('open');
      alert('✅ Application submitted successfully!');
      window.location.reload();
    } catch (err) {
      alert(err.message || 'Failed to submit application');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Application →';
    }
  };

  // Close modal on overlay click
  document.getElementById('applyModal').onclick = (e) => {
    if (e.target.id === 'applyModal') {
      document.getElementById('applyModal').classList.remove('open');
    }
  };
}

async function loadJobs() {
  const container = document.querySelector('.jobs-list');
  if (!container) return;

  try {
    const jobs = await apiRequest('/v1/jobs');
    renderJobs(jobs);
  } catch (err) {
    console.error('Failed to load jobs:', err);
  }
}

function renderJobs(jobs) {
  const container = document.querySelector('.jobs-list');
  if (!container) return;

  if (jobs.length === 0) {
    container.innerHTML = '<div class="empty-state">No jobs found matching your criteria.</div>';
    return;
  }

  container.innerHTML = jobs.map(job => `
    <div class="job-card ${job.urgency === 'urgent' ? 'urgent' : ''}" onclick="window.location.href='job-detail.html?id=${job.id}'">
      <div class="jc-top">
        <div class="jc-icon">${getTradeIcon(job.trade)}</div>
        <div class="jc-info">
          <div class="jc-title">${job.title} ${job.urgency === 'urgent' ? '<span class="utag utag-urgent">Urgent</span>' : ''}</div>
          <div class="jc-meta">
            <span>📍 ${job.area || job.county}</span>
            <span>${formatTimeAgo(job.created_at)}</span>
            <span>${job.applications_count || 0} applicants</span>
          </div>
        </div>
        <div class="jc-right">
          <div class="jc-budget">KES ${job.budget_min.toLocaleString()} - ${job.budget_max.toLocaleString()}</div>
          <div class="jc-budget-sub">${job.payment_type}</div>
        </div>
      </div>
      <div class="jc-desc">${job.description}</div>
      <div class="jc-footer">
        <div class="jc-client"><div class="jc-client-av">👤</div>${job.client?.full_name || 'Client'} · ★★★★★ ${job.client?.rating || '5.0'}</div>
        <button class="apply-btn" onclick="event.stopPropagation(); openApply('${job.title}', '${job.id}')">Apply →</button>
      </div>
    </div>
  `).join('');
}

function getTradeIcon(trade) {
  const icons = {
    plumber: '🚿', electrician: '⚡', mason: '🧱', mama_fua: '👗',
    carpenter: '🪚', painter: '🎨', roofer: '🏠', gardener: '🌿',
    driver_mover: '🛻', security: '🔒'
  };
  return icons[trade] || '🛠️';
}

// Auto-init
if (document.querySelector('.jobs-list')) {
  initWorkerJobs();
}
