/**
 * supabase/client.js
 * ──────────────────
 * Initialises and exports the Supabase anon client for all frontend pages.
 *
 * Usage (CDN / no build step):
 *   <script type="module">
 *     import { supabase } from './supabase/client.js';
 *   </script>
 *
 * Usage (npm / bundler):
 *   import { supabase } from '@/supabase/client';
 */

// CDN import — swap for npm import if using a bundler:
// import { createClient } from '@supabase/supabase-js';
import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

const injectedEnv = typeof window !== 'undefined' ? window.__KAZIX_ENV__ : undefined;

function parseDotEnv(text) {
  const env = {};
  for (const rawLine of text.split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    if (line.startsWith('export ')) line = line.slice(7).trim();

    const idx = line.indexOf('=');
    if (idx <= 0) continue;

    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();

    const hasDoubleQuotes = value.startsWith('"') && value.endsWith('"');
    const hasSingleQuotes = value.startsWith("'") && value.endsWith("'");
    if (hasDoubleQuotes || hasSingleQuotes) value = value.slice(1, -1);

    env[key] = value;
  }
  return env;
}

async function loadFrontendEnv() {
  if (typeof window === 'undefined' || typeof fetch !== 'function') return {};

  // '/.env' when serving `frontend/` as web root.
  // '/frontend/.env' when serving repository root as web root.
  const candidates = ['/.env', '/frontend/.env'];
  for (const path of candidates) {
    try {
      const response = await fetch(path, { cache: 'no-store' });
      if (!response.ok) continue;
      return parseDotEnv(await response.text());
    } catch {
      // Keep trying next location.
    }
  }
  return {};
}

const fileEnv = await loadFrontendEnv();
const SUPABASE_URL = import.meta.env?.VITE_SUPABASE_URL
  ?? injectedEnv?.SUPABASE_URL
  ?? fileEnv.VITE_SUPABASE_URL
  ?? fileEnv.SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env?.VITE_SUPABASE_ANON_KEY
  ?? injectedEnv?.SUPABASE_ANON_KEY
  ?? fileEnv.VITE_SUPABASE_ANON_KEY
  ?? fileEnv.SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // Graceful fallback for local development if not injected
  console.warn('[KaziX] Supabase URL and anon key not found. Set VITE_SUPABASE_* or SUPABASE_* in frontend/.env.');
}

/**
 * Anon Supabase client — safe for browser use.
 * All queries respect RLS policies.
 */
export const supabase = createClient(SUPABASE_URL || '', SUPABASE_ANON_KEY || '', {
  auth: {
    persistSession:    true,
    autoRefreshToken:  true,
    detectSessionInUrl: false,
  },
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
});

/**
 * Convenience: get the current session's user object.
 * Returns null if not authenticated.
 */
export async function getCurrentUser() {
  const { data: { user } } = await supabase.auth.getUser();
  return user;
}

/**
 * Convenience: get the current session tokens.
 */
export async function getSession() {
  const { data: { session } } = await supabase.auth.getSession();
  return session;
}
