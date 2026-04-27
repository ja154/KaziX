(function () {
  /**
   * Error message mapping
   * Maps backend error codes and messages to user-friendly messages
   */

  const ERROR_MESSAGES = {
    // Authentication errors
    401: {
      title: 'Session Expired',
      message: 'Your session has expired. Please log in again to continue.',
      code: 'UNAUTHORIZED',
    },
    403: {
      title: 'Access Denied',
      message: 'You do not have permission to perform this action.',
      code: 'FORBIDDEN',
    },

    // Validation errors
    422: {
      title: 'Invalid Input',
      message: 'Please check your input and try again.',
      code: 'VALIDATION_ERROR',
    },

    // Not found errors
    404: {
      title: 'Not Found',
      message: 'The resource you are looking for was not found.',
      code: 'NOT_FOUND',
    },

    // Server errors
    500: {
      title: 'Server Error',
      message: 'Something went wrong on our end. Our team has been notified.',
      code: 'INTERNAL_ERROR',
    },
    502: {
      title: 'Service Unavailable',
      message: 'Our service is temporarily unavailable. Please try again later.',
      code: 'BAD_GATEWAY',
    },
    503: {
      title: 'Service Unavailable',
      message: 'Our service is temporarily unavailable. Please try again later.',
      code: 'SERVICE_UNAVAILABLE',
    },

    // Network errors
    NETWORK_ERROR: {
      title: 'Connection Error',
      message: 'No internet connection. Please check your connection and try again.',
      code: 'NETWORK_ERROR',
    },
    TIMEOUT: {
      title: 'Request Timeout',
      message: 'The request took too long. Please check your connection and try again.',
      code: 'TIMEOUT',
    },

    // Default
    DEFAULT: {
      title: 'Error',
      message: 'An unexpected error occurred. Please try again.',
      code: 'UNKNOWN_ERROR',
    },
  };

  /**
   * Get user-friendly error message from status code or error key
   * @param {number|string} codeOrKey - HTTP status code or error key
   * @param {object} options - Additional options
   * @param {string} options.detail - Detailed error message from backend
   * @param {string} options.message - Additional message context
   * @returns {object} - { title, message, code, details }
   */
  function getErrorMessage(codeOrKey, options = {}) {
    const key = String(codeOrKey);
    const config = ERROR_MESSAGES[key] || ERROR_MESSAGES.DEFAULT;

    // If backend provided a detail message, use it as additional info
    let details = options.detail || options.message;
    if (details && typeof details === 'string') {
      details = details.trim();
      // Remove redundant error codes from details
      if (details.length > 100) {
        details = details.substring(0, 97) + '...';
      }
    }

    return {
      title: config.title,
      message: config.message,
      code: config.code,
      details: details || null,
    };
  }

  /**
   * Map common API error patterns to user-friendly messages
   * @param {object} error - Error object from failed fetch/API call
   * @returns {object} - { title, message, code, details }
   */
  function mapApiError(error) {
    // Network error
    if (!error.status && error.message && error.message.includes('fetch')) {
      return getErrorMessage('NETWORK_ERROR');
    }

    // Timeout
    if (error.name === 'AbortError' || error.message === 'The user aborted a request.') {
      return getErrorMessage('TIMEOUT');
    }

    // HTTP error status
    if (error.status) {
      // Special case: auth errors should redirect
      if (error.status === 401 || error.status === 403) {
        return {
          ...getErrorMessage(error.status),
          shouldRedirect: true,
          redirectTo: 'login.html',
        };
      }

      return getErrorMessage(error.status, {
        detail: error.detail || error.message,
      });
    }

    // Unknown error
    return getErrorMessage('DEFAULT', {
      message: error.message || 'Unknown error',
    });
  }

  /**
   * Extract validation errors from 422 response
   * @param {object} errorResponse - Response object from API
   * @returns {object} - { fieldName: 'error message', ... }
   */
  function extractValidationErrors(errorResponse) {
    const errors = {};

    if (!errorResponse) return errors;

    // FastAPI-style validation errors
    if (Array.isArray(errorResponse.detail)) {
      errorResponse.detail.forEach((err) => {
        if (err.loc && err.loc.length >= 2) {
          const field = err.loc[err.loc.length - 1]; // Get field name from location path
          errors[field] = err.msg || 'Invalid input';
        }
      });
    }

    // Custom validation error format
    if (typeof errorResponse.details === 'object' && !Array.isArray(errorResponse.details)) {
      Object.assign(errors, errorResponse.details);
    }

    // Single detail message
    if (errorResponse.details && Array.isArray(errorResponse.details)) {
      errorResponse.details.forEach((detail, index) => {
        errors[`field_${index}`] = detail;
      });
    }

    return errors;
  }

  /**
   * Format error for display (removes sensitive info)
   * @param {string|Error} error - Error to format
   * @returns {string} - Safe error message
   */
  function formatErrorMessage(error) {
    if (!error) return 'An unknown error occurred';

    if (typeof error === 'string') {
      return error.trim();
    }

    if (error.message) {
      return error.message.trim();
    }

    return String(error).trim();
  }

  // Export to window
  window.KazixErrorMessages = {
    getErrorMessage,
    mapApiError,
    extractValidationErrors,
    formatErrorMessage,
    ERROR_MESSAGES,
  };
})();
