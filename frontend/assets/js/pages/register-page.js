/**
 * pages/register-page.js
 * ──────────────────────
 * Wires up register.html to real OTP, verification, and profile creation.
 */

import { sendOTP as apiSendOTP } from '../auth/send-otp.js';
import { verifyOTP as apiVerifyOTP } from '../auth/verify-otp.js';
import { submitRegistrationForm } from '../auth/create-profile.js';

let regRole = 'client';
let regCurrentStep = 1;
let accessToken = null;

export function initRegister() {
  // Step 1: Type Selection
  const typeCards = document.querySelectorAll('.type-card');
  typeCards.forEach(card => {
    card.onclick = () => {
      regRole = card.id === 'typePro' ? 'fundi' : 'client';
      typeCards.forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
    };
  });

  // Step 2: Next button to Step 2 is in HTML, let's wire it
  window.goRStep = (n) => goRStep(n);

  // Trade selection
  const tradeChips = document.querySelectorAll('.trade-chip, .trade-option');
  tradeChips.forEach(chip => {
    chip.onclick = () => {
      tradeChips.forEach(c => c.classList.remove('selected'));
      chip.classList.add('selected');
    };
  });

  // OTP inputs
  const otpDigits = document.querySelectorAll('#rstep3 .otp-digit');
  otpDigits.forEach((digit, idx) => {
    digit.oninput = () => {
      digit.value = digit.value.replace(/[^0-9]/g, '');
      if (digit.value && idx < 5) {
        otpDigits[idx + 1].focus();
      }
      checkRegOtpComplete();
    };

    digit.onkeydown = (e) => {
      if (e.key === 'Backspace' && !digit.value && idx > 0) {
        otpDigits[idx - 1].focus();
      }
    };
  });

  // Verification
  const regVerifyBtn = document.getElementById('regVerifyBtn');
  regVerifyBtn.onclick = async () => {
    const phone = '+254' + document.getElementById('regPhone').value.replace(/\s/g, '');
    const code = Array.from(otpDigits).map(d => d.value).join('');

    regVerifyBtn.disabled = true;
    regVerifyBtn.textContent = 'Verifying...';

    const res = await apiVerifyOTP(phone, code, false);
    if (res.success) {
      accessToken = res.access_token;
      goRStep(4);
    } else {
      alert(res.message || 'Invalid OTP');
      regVerifyBtn.disabled = false;
      regVerifyBtn.textContent = 'Verify Phone →';
    }
  };

  // Submit button
  const submitBtn = document.getElementById('submitBtn');
  submitBtn.onclick = async () => {
    if (!accessToken) {
      alert('Session expired. Please restart registration.');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating Account...';

    const res = await submitRegistrationForm(accessToken);
    if (res.success) {
      document.getElementById('rstep4').classList.remove('active');
      document.getElementById('stepProgress').style.display = 'none';
      const successEl = document.getElementById('regSuccess');
      successEl.classList.add('show');

      if (regRole === 'fundi') {
        document.getElementById('successEmoji').textContent = '🔧';
        document.getElementById('successTitle').textContent = 'Welcome to KaziX!';
        document.getElementById('successSub').textContent = 'Your profile is under review. We\'ll verify your ID within 2–4 hours and notify you by SMS. You can already browse available jobs!';

        // Update buttons for fundi
        const homeBtn = successEl.querySelector('.btn-home:first-of-type');
        const actionBtn = successEl.querySelector('.btn-home:last-of-type');
        if (homeBtn) {
          homeBtn.textContent = 'Dashboard';
          homeBtn.href = 'index.html';
        }
        if (actionBtn) {
          actionBtn.textContent = 'Browse Jobs';
          actionBtn.href = 'worker-jobs.html';
          actionBtn.style.background = 'var(--green)';
        }
      }
      window.scrollTo({top:0,behavior:'smooth'});
    } else {
      alert(res.message || 'Failed to create profile');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create Account 🎉';
    }
  };
}

async function goRStep(n) {
  // If moving from step 2 to 3, send OTP
  if (regCurrentStep === 2 && n === 3) {
    const phoneVal = document.getElementById('regPhone').value.replace(/\s/g, '');
    if (phoneVal.length < 9) {
      alert('Please enter a valid phone number');
      return;
    }
    const phone = '+254' + phoneVal;
    const res = await apiSendOTP(phone);
    if (!res.success) {
      alert(res.message || 'Failed to send OTP');
      return;
    }
    document.getElementById('regSentPhone').textContent = phone;
  }

  document.getElementById('rstep' + regCurrentStep).classList.remove('active');
  const prevNode = document.getElementById('rsn' + regCurrentStep);
  prevNode.classList.remove('active');
  prevNode.classList.add('done');
  prevNode.querySelector('.rs-circle').textContent = '✓';

  regCurrentStep = n;
  document.getElementById('rstep' + n).classList.add('active');
  document.getElementById('rsn' + n).classList.add('active');

  // Toggle pro/client fields based on role
  if (n === 2) {
    document.getElementById('proFields').style.display = regRole === 'fundi' ? 'block' : 'none';
  }
  if (n === 4) {
    document.getElementById('proProfile').style.display = regRole === 'fundi' ? 'block' : 'none';
    document.getElementById('clientProfile').style.display = regRole === 'client' ? 'block' : 'none';
    document.getElementById('step4Sub').textContent = regRole === 'fundi'
      ? 'Verify your identity to unlock more jobs and earn the verified badge'
      : 'Almost done — a few final details';
  }
  window.scrollTo({top:0,behavior:'smooth'});
}

function checkRegOtpComplete() {
  const otpDigits = document.querySelectorAll('#rstep3 .otp-digit');
  const allFilled = Array.from(otpDigits).every(d => d.value);
  document.getElementById('regVerifyBtn').disabled = !allFilled;
}

// Auto-init if on register page
if (document.getElementById('regPhone')) {
  initRegister();
}
