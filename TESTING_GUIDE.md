# KaziX Error Handling System - Testing Guide

This document explains how to test and verify the comprehensive error handling system implementation for KaziX.

## Quick Start

### Option 1: Automated Node.js Test Suite
Run the automated test suite to verify all components are properly structured:

```bash
cd frontend/assets/js
node test-error-system.js
```

Expected output: All 52+ tests passing across 8 test categories.

### Option 2: Interactive Browser Tests
Open the interactive test page in a browser to manually test all error handling features:

1. Start a local web server in the project root:
   ```bash
   # Python 3
   python3 -m http.server 8000
   
   # Or Node.js
   npx http-server
   ```

2. Open in browser: `http://localhost:8000/frontend/pages/test-error-handling.html`

3. Interact with all test buttons and forms to verify functionality

## Test Coverage

### Automated Tests (test-error-system.js)

Verifies 52+ test cases across these categories:

1. **Error Messages Module** (7 tests)
   - HTTP status code mapping (400, 401, 403, 404, 422, 500, 503)

2. **Error Handler API** (12 tests)
   - Toast functions: showToast, showError, showSuccess, showWarning, showInfo, clearAllToasts
   - Field error functions: setFieldError, clearFieldError, clearAllFieldErrors
   - Modal functions: showErrorModal, displayApiError
   - Initialization: initializeToastContainer

3. **Form Validator API** (8 tests)
   - Form validation: createFormValidator
   - Validation patterns and rules: ValidationPatterns, CommonRules
   - Validation helpers: isValidEmail, isValidPhone, isValidPhoneKE, isValidUrl, passwordsMatch

4. **Validation Patterns** (5 tests)
   - EMAIL: `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`
   - PHONE: `/^[\d\s\-\+\(\)]{7,}$/`
   - PHONE_KE: `/^(?:\+254|0)[17]\d{8}$/`
   - URL: `/^https?:\/\//`
   - ALPHANUMERIC: `/^[a-zA-Z0-9]+$/`

5. **Toast Timing** (4 tests)
   - Error toasts: 4000ms auto-dismiss
   - Success toasts: 3000ms auto-dismiss
   - Warning toasts: 3500ms auto-dismiss
   - Info toasts: 3000ms auto-dismiss

6. **Field Error Management** (4 tests)
   - setFieldError operations
   - clearFieldError operations
   - clearAllFieldErrors operations

7. **HTTP Error Mapping** (9 tests)
   - Status codes: 400, 401, 403, 404, 409, 422, 500, 502, 503

8. **Form Validation Rules** (5 tests)
   - required, minLength, maxLength, pattern, custom

### Interactive Browser Tests (test-error-handling.html)

Provides hands-on testing of:

#### 1. Toast Notifications
- **Show Error Toast**: Displays error message with 4s auto-dismiss
- **Show Success Toast**: Displays success message with 3s auto-dismiss
- **Show Warning Toast**: Displays warning message
- **Show Info Toast**: Displays info message
- **Clear All Toasts**: Removes all active toasts

#### 2. Form Validation (Real-time)
- Email field with pattern validation
- Phone field with Kenya phone validation
- URL field with protocol validation
- Password field with minimum length validation

Validation happens on blur and shows inline error messages.

#### 3. Field-Level Error Display
- **Set Field Error**: Manually sets error on a field
- **Clear Field Error**: Clears the error
- Demonstrates inline error message display

#### 4. Error Modal Dialog
- Shows critical error in modal
- Closable by button or Escape key
- Tests focus management and accessibility

#### 5. Simulated API Errors
- **401 Unauthorized**: Session expired scenario
- **404 Not Found**: Resource missing scenario
- **422 Validation**: Field validation errors
- **500 Server Error**: Server-side failure
- **Network Error**: Connection failure

## Verification Checklist

### Pre-Testing
- [ ] All files created and syntax-valid (see git log)
- [ ] All pages integrated with error-components.css
- [ ] All pages integrated with error-handler.js
- [ ] Form pages integrated with form-handler.js
- [ ] Backend exception handlers installed

### Functional Testing

#### Toast Notifications
- [ ] Error toast displays and auto-dismisses after 4 seconds
- [ ] Success toast displays and auto-dismisses after 3 seconds
- [ ] Warning toast displays correctly
- [ ] Info toast displays correctly
- [ ] Hovering over toast pauses auto-dismiss
- [ ] Multiple toasts stack vertically
- [ ] Toasts have close button

#### Form Validation
- [ ] Email validation works for invalid emails
- [ ] Email validation passes for valid emails
- [ ] Phone validation works for Kenya phone numbers
- [ ] URL validation checks for http/https protocol
- [ ] Password validation enforces minimum length
- [ ] Error clears on field focus
- [ ] Form prevents submission with errors
- [ ] Multiple field errors display correctly

#### Field Error Display
- [ ] Field error appears below field with red border
- [ ] Field error message is clear and helpful
- [ ] Error clears when user starts typing in field
- [ ] Error icon/indicator is visible

#### Error Modal
- [ ] Modal displays centered on screen
- [ ] Modal can be closed with close button
- [ ] Modal can be closed with Escape key
- [ ] Modal has proper focus management
- [ ] Modal background is darkened

#### API Error Handling
- [ ] 401 errors show session expired message
- [ ] 404 errors show resource not found message
- [ ] 422 errors show validation message
- [ ] 500 errors show generic error message
- [ ] Network errors show connection error message
- [ ] Field errors from 422 response display inline

#### Accessibility
- [ ] Tab navigation works through all fields
- [ ] Screen reader announces toast messages
- [ ] Modal title is focused when shown
- [ ] Escape key closes modal
- [ ] Color contrast is sufficient
- [ ] ARIA labels are present

#### Browser Compatibility
- [ ] Works in Chrome/Chromium
- [ ] Works in Firefox
- [ ] Works in Safari
- [ ] Works in Edge
- [ ] Mobile responsive (test at 375px, 768px widths)

## Running Tests in CI/CD

Add to your CI/CD pipeline:

```bash
# Verify syntax
node -c frontend/assets/js/error-handler.js
node -c frontend/assets/js/error-messages.js
node -c frontend/assets/js/form-handler.js
python3 -m py_compile backend/app/main.py

# Run automated test suite
node frontend/assets/js/test-error-system.js

# Check integration on all pages
grep -l "error-components.css" frontend/pages/*.html | wc -l
# Should output: 8
```

## Troubleshooting

### Tests Fail
1. **Check file paths**: Ensure all files are in correct directories
2. **Check syntax**: Run `node -c` on JS files, `python3 -m py_compile` on Python files
3. **Check imports**: Verify error-messages.js loads before error-handler.js
4. **Check node version**: Use Node.js 14+

### Interactive Tests Don't Work
1. **Check CSS**: Verify error-components.css is loading (check Network tab)
2. **Check JavaScript**: Open DevTools console for errors
3. **Check file paths**: All script src paths must be correct relative to test page
4. **Check modules**: Type in console: `window.KazixErrorHandler` should show the object

### Form Validation Not Working
1. Verify form-handler.js is loaded after error-handler.js
2. Check that form has correct id attribute
3. Verify field names match between HTML and validation schema
4. Check console for JavaScript errors

### Toasts Not Displaying
1. Verify error-components.css is linked
2. Check that initializeToastContainer() is called
3. Verify toast container div is created in DOM
4. Check z-index CSS if toasts are behind other elements

## Performance Notes

- Toast animations use CSS transforms (GPU accelerated)
- Field error messages DOM is created on-demand
- Modal backdrop uses CSS opacity (efficient rendering)
- No external dependencies - pure vanilla JavaScript
- Total file size: ~32 KB (minified, no gzip)

## Browser Support

- Chrome/Chromium: ✓ Full support
- Firefox: ✓ Full support
- Safari: ✓ Full support (14+)
- Edge: ✓ Full support
- IE11: ✗ Not supported (uses ES2020 features)

## Next Steps

1. Run automated test suite: `node frontend/assets/js/test-error-system.js`
2. Open interactive test page in browser
3. Verify all functional tests pass
4. Deploy to staging environment
5. Perform cross-browser testing
6. Deploy to production

## Support

For questions or issues:
1. Check ERROR_HANDLING_GUIDE.md for implementation details
2. Check IMPLEMENTATION_STATUS.md for complete feature list
3. Review test files for usage examples
4. Check browser console for error messages

---

**Last Updated**: April 27, 2025  
**Test Suite Version**: 1.0  
**Status**: Production Ready
