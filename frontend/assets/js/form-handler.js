(function () {
  /**
   * Form Validation & Error Display Handler
   * Provides client-side form validation with integrated error display
   */

  /**
   * Create a form validator instance
   * @param {HTMLElement|string} form - Form element or selector
   * @param {object} schema - Validation schema { fieldName: { required, minLength, pattern, custom, message } }
   * @returns {object} - Validator instance with validate() method
   */
  function createFormValidator(form, schema = {}) {
    const formEl = typeof form === 'string' ? document.querySelector(form) : form;
    if (!formEl) {
      console.error('Form element not found');
      return null;
    }

    const validator = {
      form: formEl,
      schema,
      errors: {},

      /**
       * Validate a single field
       * @param {string} fieldName - Field name
       * @param {*} value - Field value
       * @returns {string|null} - Error message or null if valid
       */
      validateField(fieldName, value) {
        const rules = this.schema[fieldName];
        if (!rules) return null;

        // Required validation
        if (rules.required && (!value || (typeof value === 'string' && !value.trim()))) {
          return rules.message || `${fieldName} is required`;
        }

        // Skip further validation if empty and not required
        if (!value && !rules.required) return null;

        // Min length validation
        if (rules.minLength && value && String(value).length < rules.minLength) {
          return rules.message || `${fieldName} must be at least ${rules.minLength} characters`;
        }

        // Max length validation
        if (rules.maxLength && value && String(value).length > rules.maxLength) {
          return rules.message || `${fieldName} must be at most ${rules.maxLength} characters`;
        }

        // Pattern validation
        if (rules.pattern && value) {
          const pattern = typeof rules.pattern === 'string' ? new RegExp(rules.pattern) : rules.pattern;
          if (!pattern.test(String(value))) {
            return rules.message || `${fieldName} format is invalid`;
          }
        }

        // Custom validation
        if (rules.custom && typeof rules.custom === 'function') {
          const result = rules.custom(value);
          if (result !== true) {
            return result === false ? (rules.message || `${fieldName} is invalid`) : result;
          }
        }

        return null;
      },

      /**
       * Validate entire form
       * @returns {boolean} - True if valid, false if errors exist
       */
      validate() {
        this.errors = {};
        let isValid = true;

        Object.keys(this.schema).forEach((fieldName) => {
          const field = this.form.querySelector(`[name="${fieldName}"], #${fieldName}`);
          if (!field) return;

          const value = field.value || field.textContent;
          const error = this.validateField(fieldName, value);

          if (error) {
            this.errors[fieldName] = error;
            window.KazixErrorHandler?.setFieldError(fieldName, error);
            isValid = false;
          } else {
            window.KazixErrorHandler?.clearFieldError(fieldName);
          }
        });

        return isValid;
      },

      /**
       * Clear all field errors
       */
      clearErrors() {
        this.errors = {};
        window.KazixErrorHandler?.clearAllFieldErrors(this.form);
      },

      /**
       * Get error for specific field
       * @param {string} fieldName - Field name
       * @returns {string|null} - Error message or null
       */
      getError(fieldName) {
        return this.errors[fieldName] || null;
      },

      /**
       * Get all errors
       * @returns {object} - { fieldName: errorMessage, ... }
       */
      getErrors() {
        return { ...this.errors };
      },

      /**
       * Setup real-time validation on blur
       */
      setupBlurValidation() {
        Object.keys(this.schema).forEach((fieldName) => {
          const field = this.form.querySelector(`[name="${fieldName}"], #${fieldName}`);
          if (!field) return;

          field.addEventListener('blur', () => {
            const value = field.value || field.textContent;
            const error = this.validateField(fieldName, value);

            if (error) {
              window.KazixErrorHandler?.setFieldError(fieldName, error);
              this.errors[fieldName] = error;
            } else {
              window.KazixErrorHandler?.clearFieldError(fieldName);
              delete this.errors[fieldName];
            }
          });
        });
      },

      /**
       * Setup validation on form submission
       * @param {function} onSubmit - Callback if form is valid
       * @returns {function} - Unsubscribe function
       */
      onSubmit(onSubmit) {
        const handleSubmit = async (e) => {
          e.preventDefault();

          if (!this.validate()) {
            window.KazixErrorHandler?.showError('Please fix the errors above and try again.', {
              title: 'Validation Error',
            });
            return;
          }

          try {
            await onSubmit(new FormData(this.form));
          } catch (error) {
            console.error('Form submission error:', error);
            window.KazixErrorHandler?.showError(
              error.message || 'An error occurred while submitting the form.',
              { title: 'Submission Error' }
            );
          }
        };

        this.form.addEventListener('submit', handleSubmit);

        // Return unsubscribe function
        return () => {
          this.form.removeEventListener('submit', handleSubmit);
        };
      },
    };

    return validator;
  }

  /**
   * Common validation patterns
   */
  const ValidationPatterns = {
    EMAIL: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
    PHONE: /^[\d\s\-\+\(\)]{7,}$/,
    URL: /^https?:\/\/.+\..+$/,
    PHONE_KE: /^(?:\+254|0)[17]\d{8}$/,
    ALPHANUMERIC: /^[a-zA-Z0-9]+$/,
    LETTERS_ONLY: /^[a-zA-Z\s]+$/,
    NUMBERS_ONLY: /^\d+$/,
  };

  /**
   * Common validation rules
   */
  const CommonRules = {
    required: (fieldName = 'This field') => ({
      required: true,
      message: `${fieldName} is required`,
    }),
    email: {
      pattern: ValidationPatterns.EMAIL,
      message: 'Please enter a valid email address',
    },
    password: {
      minLength: 8,
      message: 'Password must be at least 8 characters',
    },
    phone: {
      pattern: ValidationPatterns.PHONE,
      message: 'Please enter a valid phone number',
    },
    url: {
      pattern: ValidationPatterns.URL,
      message: 'Please enter a valid URL',
    },
    minLength: (length) => ({
      minLength: length,
      message: `Must be at least ${length} characters`,
    }),
    maxLength: (length) => ({
      maxLength: length,
      message: `Must be at most ${length} characters`,
    }),
  };

  /**
   * Validate email address
   * @param {string} email - Email to validate
   * @returns {boolean} - True if valid
   */
  function isValidEmail(email) {
    return ValidationPatterns.EMAIL.test(String(email));
  }

  /**
   * Validate phone number (Kenya format or international)
   * @param {string} phone - Phone number to validate
   * @returns {boolean} - True if valid
   */
  function isValidPhone(phone) {
    return ValidationPatterns.PHONE.test(String(phone));
  }

  /**
   * Validate Kenya phone number specifically
   * @param {string} phone - Phone number to validate
   * @returns {boolean} - True if valid
   */
  function isValidPhoneKE(phone) {
    return ValidationPatterns.PHONE_KE.test(String(phone));
  }

  /**
   * Validate URL
   * @param {string} url - URL to validate
   * @returns {boolean} - True if valid
   */
  function isValidUrl(url) {
    return ValidationPatterns.URL.test(String(url));
  }

  /**
   * Match password confirmation
   * @param {string} password - Password
   * @param {string} confirm - Confirmation password
   * @returns {boolean} - True if match
   */
  function passwordsMatch(password, confirm) {
    return password === confirm;
  }

  // Export to window
  window.KazixFormValidator = {
    createFormValidator,
    ValidationPatterns,
    CommonRules,
    isValidEmail,
    isValidPhone,
    isValidPhoneKE,
    isValidUrl,
    passwordsMatch,
  };
})();
