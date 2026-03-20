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

const SUPABASE_URL      = import.meta.env?.VITE_SUPABASE_URL      ?? window.__KAZIX_ENV__?.SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env?.VITE_SUPABASE_ANON_KEY ?? window.__KAZIX_ENV__?.SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // Graceful fallback for local development if not injected
  console.warn('[KaziX] Supabase URL and anon key not found. Ensure they are set via window.__KAZIX_ENV__ or .env.');
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
