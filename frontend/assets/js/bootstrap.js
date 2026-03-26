/**
 * bootstrap.js
 * ────────────
 * Unified loader that detects the current page and imports the relevant module.
 * Usage: Add <script type="module" src="../assets/js/bootstrap.js"></script>
 */

const pageMap = {
  'login.html':           './pages/login-page.js',
  'register.html':        './pages/register-page.js',
  'post-job.html':        './pages/post-job-page.js',
  'job-applicants.html':  './pages/job-applicants-page.js',
  'my-hires.html':        './pages/my-hires-page.js',
  'worker-jobs.html':     './pages/worker-jobs-page.js',
  'dispute.html':         './pages/dispute-page.js',
  'messages.html':        './pages/messages-page.js',
  'notifications.html':   './pages/notifications-page.js',
};

async function bootstrap() {
  const pathParts = window.location.pathname.split('/');
  const page = pathParts[pathParts.length - 1] || 'index.html';

  const modulePath = pageMap[page];
  if (modulePath) {
    try {
      await import(modulePath);
      console.log(`[KaziX] Bootstrapped ${page} with ${modulePath}`);
    } catch (err) {
      console.error(`[KaziX] Failed to load module for ${page}:`, err);
    }
  }
}

bootstrap();
