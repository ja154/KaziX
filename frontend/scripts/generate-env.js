const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const envPath = path.join(root, '.env');
const outPath = path.join(root, 'env.js');

// --- Patch: Create .env from process.env if missing (for Vercel build) ---
if (!fs.existsSync(envPath)) {
  // List all required env vars here
  const envVars = [
    'VITE_SUPABASE_URL',
    'VITE_SUPABASE_ANON_KEY',
    'SUPABASE_REDIRECT_URL',
    'SUPABASE_URL',
    'SUPABASE_ANON_KEY',
    'GOOGLE_CLIENT_ID',
    'GOOGLE_CLIENT_SECRET',
    'OAUTH_REDIRECT_URI',
    'API_BASE_URL',
    'VITE_API_URL',
    'KAZIX_API_BASE',
    'BACKEND_API_URL',
  ];
  const envContent = envVars
    .map(key => `${key}=${process.env[key] || ''}`)
    .join('\n');
  fs.writeFileSync(envPath, envContent);
}

if (!fs.existsSync(envPath)) {
  throw new Error('frontend/.env not found. Create it with SUPABASE_URL and SUPABASE_ANON_KEY.');
}

const lines = fs.readFileSync(envPath, 'utf8').split(/\r?\n/);
const vars = {};
for (const rawLine of lines) {
  const line = rawLine.trim();
  if (!line || line.startsWith('#')) continue;
  const idx = line.indexOf('=');
  if (idx === -1) continue;
  const key = line.slice(0, idx).trim();
  let value = line.slice(idx + 1).trim();
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    value = value.slice(1, -1);
  }
  vars[key] = value;
}

const supabaseUrl = vars.VITE_SUPABASE_URL || vars.SUPABASE_URL;
const supabaseAnonKey = vars.VITE_SUPABASE_ANON_KEY || vars.SUPABASE_ANON_KEY;
const supabaseRedirectUrl = vars.SUPABASE_REDIRECT_URL || null;
const apiBase =
  vars.KAZIX_API_BASE ||
  vars.API_BASE_URL ||
  vars.VITE_API_URL ||
  vars.BACKEND_API_URL ||
  null;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY (or SUPABASE_URL/SUPABASE_ANON_KEY) in frontend/.env.');
}

const config = {
  SUPABASE_URL: supabaseUrl,
  SUPABASE_ANON_KEY: supabaseAnonKey,
  ...(apiBase ? { KAZIX_API_BASE: apiBase.replace(/\/$/, '') } : {}),
  ...(supabaseRedirectUrl ? { SUPABASE_REDIRECT_URL: supabaseRedirectUrl } : {}),
};

const content = `// Generated from frontend/.env. Do not edit directly.
(function () {
  const config = ${JSON.stringify(config, null, 2)};
  const DEFAULT_REMOTE_API_BASE = 'https://kazix.onrender.com';

  function isLocalHost(host) {
    return ['localhost', '127.0.0.1', '0.0.0.0'].includes(host);
  }

  function normalizeApiBase(candidate) {
    if (!candidate) {
      return null;
    }

    try {
      const url = new URL(candidate, window.location.origin);
      if (url.origin === window.location.origin && url.pathname === '/') {
        return '';
      }
      return url.toString().replace(/\\/$/, '');
    } catch (_error) {
      return candidate.replace(/\\/$/, '');
    }
  }

  function inferApiBase() {
    const host = window.location.hostname;
    if (isLocalHost(host)) {
      return window.location.origin.replace(/\\/$/, '');
    }

    return DEFAULT_REMOTE_API_BASE;
  }

  function resolveApiBase() {
    const configuredApiBase = normalizeApiBase(config.KAZIX_API_BASE);
    return configuredApiBase ?? inferApiBase();
  }

  window.KAZIX_CONFIG = config;
  window.SUPABASE_URL = window.SUPABASE_URL || config.SUPABASE_URL;
  window.SUPABASE_ANON_KEY = window.SUPABASE_ANON_KEY || config.SUPABASE_ANON_KEY;
  window.KAZIX_API_BASE = window.KAZIX_API_BASE || resolveApiBase();
  window.SUPABASE_REDIRECT_URL = window.SUPABASE_REDIRECT_URL || config.SUPABASE_REDIRECT_URL;
})();
`;

fs.writeFileSync(outPath, content, 'utf8');
console.log(`Wrote ${path.relative(process.cwd(), outPath)} from ${path.relative(process.cwd(), envPath)}`);
