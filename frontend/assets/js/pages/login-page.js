/**
 * pages/login-page.js
 * ───────────────────
 * Wires up login.html to real OTP flow via /v1/auth/send-otp and /v1/auth/verify-otp.
 */

import { sendOTP as apiSendOTP } from '../auth/send-otp.js';
import { verifyOTP as apiVerifyOTP } from '../auth/verify-otp.js';

let countdownTimer;
let currentRole = 'client';

export function initLogin() {
  const roleOptions = document.querySelectorAll('.role-option');
  roleOptions.forEach(opt => {
    opt.onclick = () => {
      currentRole = opt.innerText.includes('Fundi') && !opt.innerText.includes('need') ? 'pro' : 'client';
      roleOptions.forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
    };
  });

  const phoneInput = document.getElementById('phoneInput');
  const sendOtpBtn = document.getElementById('sendOtpBtn');

  phoneInput.oninput = () => {
    const phone = phoneInput.value.replace(/\s/g, '');
    sendOtpBtn.disabled = phone.length < 9;
  };

  sendOtpBtn.onclick = async () => {
    const phone = '+254' + phoneInput.value.replace(/\s/g, '');
    sendOtpBtn.disabled = true;
    sendOtpBtn.textContent = 'Sending...';

    const res = await apiSendOTP(phone);
    if (res.success) {
      document.getElementById('sentPhone').textContent = phone;
      document.getElementById('phoneStep').style.display = 'none';
      document.getElementById('otpStep').classList.add('show');
      document.querySelectorAll('.otp-digit')[0].focus();
      startCountdown();
    } else {
      alert(res.message || 'Failed to send OTP');
      sendOtpBtn.disabled = false;
      sendOtpBtn.textContent = 'Send OTP →';
    }
  };

  const otpDigits = document.querySelectorAll('.otp-digit');
  otpDigits.forEach((digit, idx) => {
    digit.oninput = (e) => {
      digit.value = digit.value.replace(/[^0-9]/g, '');
      if (digit.value && idx < 5) {
        otpDigits[idx + 1].focus();
      }
      checkOtpComplete();
    };

    digit.onkeydown = (e) => {
      if (e.key === 'Backspace' && !digit.value && idx > 0) {
        otpDigits[idx - 1].focus();
      }
    };
  });

  const verifyBtn = document.getElementById('verifyBtn');
  verifyBtn.onclick = async () => {
    const phone = '+254' + phoneInput.value.replace(/\s/g, '');
    const code = Array.from(otpDigits).map(d => d.value).join('');

    verifyBtn.disabled = true;
    verifyBtn.textContent = 'Verifying...';

    // We pass false to autoRedirect because we handle redirection here
    // based on the role selected in the UI.
    const res = await apiVerifyOTP(phone, code, false);
    if (res.success) {
      const urlParams = new URLSearchParams(window.location.search);
      const redirect = urlParams.get('redirect');
      if (redirect) {
        window.location.href = redirect;
      } else {
        window.location.href = currentRole === 'pro' ? 'worker-jobs.html' : 'index.html';
      }
    } else {
      alert(res.message || 'Invalid OTP');
      verifyBtn.disabled = false;
      verifyBtn.textContent = 'Verify & Sign In';
    }
  };

  window.resendOTP = async () => {
    const phone = '+254' + phoneInput.value.replace(/\s/g, '');
    const res = await apiSendOTP(phone);
    if (res.success) {
      otpDigits.forEach(d => d.value = '');
      otpDigits[0].focus();
      startCountdown();
    } else {
      alert(res.message || 'Failed to resend OTP');
    }
  };

  window.changePhone = () => {
    document.getElementById('phoneStep').style.display = 'block';
    document.getElementById('otpStep').classList.remove('show');
    clearInterval(countdownTimer);
    sendOtpBtn.disabled = false;
    sendOtpBtn.textContent = 'Send OTP →';
  };
}

function checkOtpComplete() {
  const otpDigits = document.querySelectorAll('.otp-digit');
  const allFilled = Array.from(otpDigits).every(d => d.value);
  document.getElementById('verifyBtn').disabled = !allFilled;
}

function startCountdown() {
  let secs = 60;
  const countdownEl = document.getElementById('countdown');
  const resendBtn = document.getElementById('resendBtn');

  countdownEl.textContent = secs;
  resendBtn.disabled = true;

  clearInterval(countdownTimer);
  countdownTimer = setInterval(() => {
    secs--;
    countdownEl.textContent = secs;
    if (secs <= 0) {
      clearInterval(countdownTimer);
      resendBtn.disabled = false;
      resendBtn.innerHTML = 'Resend OTP';
    }
  }, 1000);
}

// Auto-init if on login page
if (document.getElementById('phoneInput')) {
  initLogin();
}
