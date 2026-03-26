/**
 * pages/post-job-page.js
 * ──────────────────────
 * Wires up post-job.html to real POST /v1/jobs via apiRequest.
 */

import { apiRequest } from '../api/client.js';

let currentStep = 1;
let selectedTrade = 'electrician';
let urgency = 'normal';

export function initPostJob() {
  const tradeOptions = document.querySelectorAll('.trade-option');
  tradeOptions.forEach(opt => {
    opt.onclick = () => {
      tradeOptions.forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
      selectedTrade = getTradeKey(opt.querySelector('.t-name').textContent);
    };
  });

  const urgencyOptions = document.querySelectorAll('.urgency-option');
  urgencyOptions.forEach(opt => {
    opt.onclick = () => {
      urgencyOptions.forEach(o => o.classList.remove('selected', 'normal'));
      opt.classList.add('selected');
      if (opt.textContent.includes('Flexible')) {
        opt.classList.add('normal');
        urgency = 'normal';
      } else {
        urgency = 'urgent';
      }
    };
  });

  window.goStep = (n) => goStep(n);
  window.submitJob = async () => {
    const title = document.querySelector('#step1 input[type="text"]').value;
    const description = document.querySelector('#step1 textarea').value;
    const county = document.querySelector('#step2 select').value;
    const area = document.querySelector('#step2 input[type="text"]').value;
    const preferredDate = document.querySelector('#step2 input[type="date"]').value;
    const preferredTime = document.querySelector('#step2 select:last-of-type').value;
    const budgetMin = parseInt(document.querySelector('#step3 input[type="number"]:first-of-type').value);
    const budgetMax = parseInt(document.querySelector('#step3 input[type="number"]:last-of-type').value);
    const paymentType = document.querySelector('#step3 select').value;

    const jobData = {
      title,
      description,
      trade: selectedTrade,
      urgency,
      county,
      area,
      preferred_date: preferredDate || undefined,
      preferred_time: preferredTime,
      budget_min: budgetMin,
      budget_max: budgetMax,
      payment_type: paymentType,
    };

    const submitBtn = document.querySelector('.btn-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Posting...';

    try {
      await apiRequest('/v1/jobs', {
        method: 'POST',
        body: jobData,
      });

      document.getElementById('step4').classList.remove('active');
      document.querySelectorAll('.step-node').forEach(n => { n.classList.remove('active'); n.classList.add('done'); });
      document.getElementById('successState').classList.add('show');
      window.scrollTo({top:0,behavior:'smooth'});
    } catch (err) {
      alert(err.message || 'Failed to post job');
      submitBtn.disabled = false;
      submitBtn.textContent = '🚀 Post Job Now';
    }
  };
}

function goStep(n) {
  document.getElementById('step'+currentStep).classList.remove('active');
  document.getElementById('snode'+currentStep).classList.remove('active');
  document.getElementById('snode'+currentStep).classList.add('done');
  currentStep = n;
  document.getElementById('step'+n).classList.add('active');
  document.getElementById('snode'+n).classList.add('active');
  window.scrollTo({top:0,behavior:'smooth'});
}

function getTradeKey(label) {
  const tradeMap = {
    'Plumber': 'plumber', 'Electrician': 'electrician', 'Mason': 'mason',
    'Mama Fua': 'mama_fua', 'Carpenter': 'carpenter', 'Painter': 'painter',
    'Roofer': 'roofer', 'Gardener': 'gardener', 'Driver/Mover': 'driver_mover',
    'Security': 'security',
  };
  return tradeMap[label] || 'other';
}

// Auto-init if on post-job page
if (document.getElementById('step1')) {
  initPostJob();
}
