/**
 * supabase/admin.js
 * ──────────────────
 * Service-role Supabase client — BYPASSES RLS.
 *
 * ⚠️  SERVER-SIDE ONLY.  Never import this in browser-executed code.
 *     Use only in:
 *       - Node.js / Deno server scripts
 *       - Admin-only tooling
 *       - Migration scripts
 *
 * The Python FastAPI backend uses its own admin client (app/core/supabase.py).
 * This file is provided for Node.js utility scripts and admin tooling.
 */

// For Node.js scripts: npm install @supabase/supabase-js
import { createClient } from '@supabase/supabase-js';
import { config }       from 'dotenv';

config(); // Load .env

const SUPABASE_URL              = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
  throw new Error('[KaziX Admin] SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env');
}

/**
 * Admin Supabase client — service role key, bypasses RLS.
 * NEVER expose to the browser or include in client bundles.
 */
export const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: {
    autoRefreshToken:  false,
    persistSession:    false,
  },
});
