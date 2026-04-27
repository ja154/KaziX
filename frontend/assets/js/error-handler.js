(function () {
  /**
   * Error Handler System
   * Provides unified error display through toasts, modals, and inline field errors
   */

  const DEFAULT_TOAST_DURATION = 4000; // ms
  const SUCCESS_TOAST_DURATION = 3000; // ms
  let toastContainer = null;
  let toastQueue = [];
  let activeToasts = new Map();

  /**
   * Initialize the toast container if not already created
   */
  function initializeToastContainer() {
    if (toastContainer) return toastContainer;

    toastContainer = document.createElement('div');
    toastContainer.id = 'toastContainer';
    toastContainer.setAttribute('role', 'region');
    toastContainer.setAttribute('aria-label', 'Notifications');
    toastContainer.setAttribute('aria-live', 'polite');
    toastContainer.setAttribute('aria-atomic', 'false');
    document.body.appendChild(toastContainer);

    return toastContainer;
  }

  /**
   * Create a toast element
   * @param {string} message - Toast message
   * @param {string} type - Toast type: 'error', 'success', 'warning', 'info'
   * @param {object} options - Additional options
   * @returns {HTMLElement} - Toast element
   */
  function createToastElement(message, type = 'info', options = {}) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.setAttribute('role', 'alert');

    const icons = {
      error: '✕',
      success: '✓',
      warning: '⚠',
      info: 'ℹ',
    };

    const titles = {
      error: 'Error',
      success: 'Success',
      warning: 'Warning',
      info: 'Info',
    };

    const icon = icons[type] || icons.info;
    const title = options.title || titles[type];

    const html = `
      <div class="toast-icon">${icon}</div>
      <div class="toast-content">
        ${title ? `<div class="toast-title">${escapeHtml(title)}</div>` : ''}
        <div class="toast-message">${escapeHtml(message)}</div>
      </div>
      <button class="toast-close" aria-label="Close notification">✕</button>
    `;

    toast.innerHTML = html;

    // Close button handler
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => {
      removeToast(toast);
    });

    return toast;
  }

  /**
   * Show a toast notification
   * @param {string} message - Toast message
   * @param {string} type - Toast type: 'error', 'success', 'warning', 'info'
   * @param {number} duration - Auto-dismiss duration in ms (0 = no auto-dismiss)
   * @param {object} options - Additional options
   */
  function showToast(message, type = 'info', duration = null, options = {}) {
    if (!message) return;

    const container = initializeToastContainer();
    const actualDuration = duration !== null ? duration : (type === 'success' ? SUCCESS_TOAST_DURATION : DEFAULT_TOAST_DURATION);

    const toast = createToastElement(message, type, options);
    container.appendChild(toast);

    // Store reference for removal
    const toastId = Date.now() + Math.random();
    activeToasts.set(toastId, toast);

    // Auto-dismiss
    if (actualDuration > 0) {
      const timeoutId = setTimeout(() => {
        removeToast(toast);
        activeToasts.delete(toastId);
      }, actualDuration);

      // Don't auto-dismiss if user is interacting
      toast.addEventListener('mouseenter', () => clearTimeout(timeoutId));
    }

    return toast;
  }

  /**
   * Remove a toast from the DOM
   * @param {HTMLElement} toast - Toast element to remove
   */
  function removeToast(toast) {
    if (!toast) return;

    toast.classList.add('exit');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300); // Match animation duration
  }

  /**
   * Show error toast
   * @param {string} message - Error message
   * @param {object} options - { title, duration, details }
   */
  function showError(message, options = {}) {
    return showToast(message, 'error', options.duration || DEFAULT_TOAST_DURATION, {
      title: options.title,
    });
  }

  /**
   * Show success toast
   * @param {string} message - Success message
   * @param {object} options - { title, duration }
   */
  function showSuccess(message, options = {}) {
    return showToast(message, 'success', options.duration || SUCCESS_TOAST_DURATION, {
      title: options.title || 'Success',
    });
  }

  /**
   * Show warning toast
   * @param {string} message - Warning message
   * @param {object} options - { title, duration }
   */
  function showWarning(message, options = {}) {
    return showToast(message, 'warning', options.duration || DEFAULT_TOAST_DURATION, {
      title: options.title || 'Warning',
    });
  }

  /**
   * Show info toast
   * @param {string} message - Info message
   * @param {object} options - { title, duration }
   */
  function showInfo(message, options = {}) {
    return showToast(message, 'info', options.duration || DEFAULT_TOAST_DURATION, {
      title: options.title,
    });
  }

  /**
   * Clear all toasts
   */
  function clearAllToasts() {
    const container = document.getElementById('toastContainer');
    if (container) {
      const toasts = container.querySelectorAll('.toast');
      toasts.forEach((toast) => removeToast(toast));
    }
    activeToasts.clear();
  }

  /**
   * Set error on a form field (inline error)
   * @param {string} fieldName - Field name or selector
   * @param {string} errorMessage - Error message to display
   */
  function setFieldError(fieldName, errorMessage) {
    const field = document.querySelector(
      `[name="${escapeHtml(fieldName)}"], #${escapeHtml(fieldName)}`
    );

    if (!field) return;

    // Create wrapper if needed
    let container = field.closest('.field-error-container');
    if (!container) {
      container = field.parentNode;
      container.classList.add('field-error-container');
    }

    // Add error class to field
    field.classList.add('error');
    container.classList.add('has-error');

    // Create or update error message element
    let errorMsg = container.querySelector('.field-error-message');
    if (!errorMsg) {
      errorMsg = document.createElement('div');
      errorMsg.className = 'field-error-message';
      container.appendChild(errorMsg);
    }
    errorMsg.textContent = errorMessage;

    // Clear error on focus
    field.addEventListener('focus', () => clearFieldError(fieldName), { once: true });
  }

  /**
   * Clear error from a form field
   * @param {string} fieldName - Field name or selector
   */
  function clearFieldError(fieldName) {
    const field = document.querySelector(
      `[name="${escapeHtml(fieldName)}"], #${escapeHtml(fieldName)}`
    );

    if (!field) return;

    const container = field.closest('.field-error-container');
    if (container) {
      field.classList.remove('error');
      container.classList.remove('has-error');
      const errorMsg = container.querySelector('.field-error-message');
      if (errorMsg) {
        errorMsg.textContent = '';
      }
    }
  }

  /**
   * Clear all field errors on a form
   * @param {HTMLElement|string} form - Form element or selector
   */
  function clearAllFieldErrors(form) {
    const formEl = typeof form === 'string' ? document.querySelector(form) : form;
    if (!formEl) return;

    const containers = formEl.querySelectorAll('.field-error-container.has-error');
    containers.forEach((container) => {
      const field = container.querySelector('[name], #');
      if (field) {
        field.classList.remove('error');
        container.classList.remove('has-error');
      }
    });
  }

  /**
   * Show error modal
   * @param {string} title - Modal title
   * @param {string} message - Modal message
   * @param {object} options - { details, onClose }
   */
  function showErrorModal(title, message, options = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'error-modal-overlay show';
    overlay.setAttribute('role', 'presentation');

    const modal = document.createElement('div');
    modal.className = 'error-modal';
    modal.setAttribute('role', 'alertdialog');
    modal.setAttribute('aria-labelledby', 'errorModalTitle');
    modal.setAttribute('aria-describedby', 'errorModalMessage');

    const detailsHtml = options.details ? `
      <div class="error-modal-details">${escapeHtml(options.details)}</div>
    ` : '';

    modal.innerHTML = `
      <div class="error-modal-header">
        <div class="error-modal-icon">⚠</div>
        <div>
          <h2 id="errorModalTitle" class="error-modal-title">${escapeHtml(title)}</h2>
        </div>
      </div>
      <p id="errorModalMessage" class="error-modal-message">${escapeHtml(message)}</p>
      ${detailsHtml}
      <div class="error-modal-actions">
        <button class="error-modal-btn error-modal-btn-primary" id="errorModalOk">
          OK
        </button>
      </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const closeModal = () => {
      overlay.classList.remove('show');
      setTimeout(() => {
        document.body.removeChild(overlay);
        if (options.onClose) options.onClose();
      }, 300);
    };

    const okBtn = modal.querySelector('#errorModalOk');
    okBtn.addEventListener('click', closeModal);

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });

    // Close on Escape key
    const handleKeydown = (e) => {
      if (e.key === 'Escape') {
        closeModal();
        document.removeEventListener('keydown', handleKeydown);
      }
    };
    document.addEventListener('keydown', handleKeydown);

    // Focus modal
    okBtn.focus();

    return overlay;
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} text - Text to escape
   * @returns {string} - Escaped text
   */
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  /**
   * Display error from API response
   * @param {object} errorResponse - Error response from API
   * @param {object} options - { showModal, fieldErrors }
   */
  function displayApiError(errorResponse, options = {}) {
    const msgConfig = window.KazixErrorMessages?.mapApiError(errorResponse) || {
      title: 'Error',
      message: 'An unexpected error occurred',
      code: 'UNKNOWN',
    };

    if (msgConfig.shouldRedirect && msgConfig.redirectTo) {
      // Redirect after showing error
      showError(msgConfig.message, { title: msgConfig.title });
      setTimeout(() => {
        window.location.href = msgConfig.redirectTo;
      }, 1500);
      return;
    }

    if (options.showModal) {
      showErrorModal(msgConfig.title, msgConfig.message, {
        details: msgConfig.details,
      });
    } else {
      showError(msgConfig.message, { title: msgConfig.title });
    }

    // Show field errors if provided
    if (options.fieldErrors && typeof options.fieldErrors === 'object') {
      Object.entries(options.fieldErrors).forEach(([field, error]) => {
        setFieldError(field, error);
      });
    }
  }

  // Export to window
  window.KazixErrorHandler = {
    initializeToastContainer,
    showToast,
    showError,
    showSuccess,
    showWarning,
    showInfo,
    clearAllToasts,
    setFieldError,
    clearFieldError,
    clearAllFieldErrors,
    showErrorModal,
    displayApiError,
  };
})();
