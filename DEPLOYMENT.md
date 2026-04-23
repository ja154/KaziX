# KaziX Deployment Guide: Vercel + Render

This repo is now wired for a `Vercel + Render` deployment:

- `frontend/` deploys to Vercel as a static site.
- `backend/` deploys to Render as a Docker web service.
- Supabase remains the hosted database and auth provider.

## What Changed In The Repo

- `frontend/package.json` gives Vercel a build step that generates `env.js`.
- `frontend/vercel.json` redirects `/` to `/pages/index.html` and disables caching for `env.js`.
- `frontend/generate-env.js` now publishes `KAZIX_API_BASE` so frontend API calls can target Render consistently.
- `render.yaml` defines a Render Blueprint for the backend service.
- `backend/app/core/config.py` now accepts `PORT` and configurable `ALLOWED_HOSTS`.
- `backend/Dockerfile` now binds Uvicorn to `PORT` when a platform sets it.

## 1. Deploy The Backend To Render

### Option A: Use The Blueprint In `render.yaml`

1. Push the repo to GitHub.
2. In Render, choose `New +` → `Blueprint`.
3. Select this repository.
4. Render will detect `render.yaml` in the repo root.
5. During setup, provide the prompted secret values:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_JWT_SECRET`
   - `MPESA_CONSUMER_KEY`
   - `MPESA_CONSUMER_SECRET`
   - `MPESA_PASSKEY`
   - `AT_API_KEY`
6. Deploy the service.

Render will create a web service named `kazix-api` with:

- Docker context: `backend/`
- Dockerfile path: `backend/Dockerfile`
- Health check: `/health`
- Default hostname: `https://kazix-api.onrender.com`

### Option B: Create The Render Service Manually

If you prefer not to use Blueprints:

1. In Render, choose `New +` → `Web Service`.
2. Connect the GitHub repo.
3. Configure the service:
   - Runtime: `Docker`
   - Dockerfile Path: `backend/Dockerfile`
   - Docker Build Context: `backend`
   - Root Directory: leave blank
   - Region: `Frankfurt`
4. Add environment variables:
   - `APP_ENV=production`
   - `APP_HOST=0.0.0.0`
   - `APP_PORT=8000`
   - `PORT=8000`
   - `LOG_LEVEL=INFO`
   - **`ALLOWED_ORIGINS=https://kazixfrontend.vercel.app`** ← Add current frontend URL (required for CORS)
   - `ALLOWED_HOSTS=localhost,127.0.0.1,kazix-api.onrender.com,api.kazix.co.ke`
   - `MPESA_ENV=sandbox`
   - `MPESA_SHORTCODE=174379`
   - `MPESA_CALLBACK_URL=https://kazix-api.onrender.com/v1/mpesa/callback`
   - `AT_USERNAME=sandbox`
   - `AT_SENDER_ID=KaziX`
5. Add the secret keys listed in Option A.
6. Set the health check path to `/health`.

## 2. Deploy The Frontend To Vercel

1. In Vercel, import the same GitHub repo.
2. Set the project root directory to `frontend`.
3. Vercel will use:
   - Build Command: `npm run build`
   - Output Directory: `.`
4. Add these environment variables in Vercel:
   - `VITE_SUPABASE_URL=https://your-project.supabase.co`
   - `VITE_SUPABASE_ANON_KEY=your-supabase-anon-key`
   - `SUPABASE_REDIRECT_URL=https://kazixfrontend.vercel.app/pages/auth-callback.html`
   - `KAZIX_API_BASE=https://kazix.onrender.com` (replace with your actual Render backend URL if different)
5. Deploy.

The checked-in `frontend/vercel.json` will make `/` load `pages/index.html`.

## 3. Update Supabase Auth Settings

Add these URLs in Supabase Auth:

- Site URL:
  - `https://kazixfrontend.vercel.app`
- Redirect URLs:
  - `http://localhost:8000/pages/auth-callback.html`
  - `https://kazixfrontend.vercel.app/pages/auth-callback.html`
  - `https://kazix.vercel.app/pages/auth-callback.html`
  - `https://kazix.co.ke/pages/auth-callback.html` if using a custom frontend domain

For Google OAuth, keep using the Supabase callback URL from your Supabase project.

## 3b. Fix CORS Errors (Cross-Origin Request Blocking)

If you see browser errors like:
```
Access to fetch at 'https://kazix-api.onrender.com/v1/auth/send-otp' 
from origin 'https://kazixfrontend.vercel.app' has been blocked by CORS policy
```

**Root Cause:** The backend's `ALLOWED_ORIGINS` environment variable does not include your frontend's URL.

**Solution:**

1. Go to **Render Dashboard** → Select `kazix-api` service → **Environment** tab
2. Find (or add) the environment variable: `ALLOWED_ORIGINS`
3. Set the value to your frontend URL(s):
   - **For current production:** `ALLOWED_ORIGINS=https://kazixfrontend.vercel.app`
   - **When adding custom domain:** `ALLOWED_ORIGINS=https://kazixfrontend.vercel.app,https://kazix.vercel.app`
4. **Save** and **Redeploy** the service
5. After redeploy, test by:
   - Opening DevTools (F12) → **Network** tab
   - Try sending an OTP or making any API call
   - Verify the preflight OPTIONS request returns status **200** with `Access-Control-Allow-Origin` response header
   - If fixed, the POST request should also succeed

For more details, see the template at `backend/.env.production.example`.

## 4. Custom Domains

Recommended production setup:

- Frontend on Vercel:
  - `kazix.co.ke`
- Backend on Render:
  - `api.kazix.co.ke`

When you add the backend custom domain, update:

- Render env var:
  - `ALLOWED_HOSTS=localhost,127.0.0.1,*.onrender.com,api.kazix.co.ke`
- Render env var:
  - `MPESA_CALLBACK_URL=https://api.kazix.co.ke/v1/mpesa/callback`
- Vercel env var:
  - `VITE_API_URL=https://api.kazix.co.ke`
- Vercel env var:
  - `SUPABASE_REDIRECT_URL=https://kazix.co.ke/pages/auth-callback.html`

## 5. Verify The Deployment

Backend checks:

```bash
curl https://kazix-api.onrender.com/health
```

Expected response:

```json
{"status":"ok","env":"production"}
```

Frontend checks:

1. Open `https://kazixfrontend.vercel.app/`
2. Confirm the landing page loads.
3. Open `https://kazixfrontend.vercel.app/pages/login.html`
4. Confirm login and auth bootstrap calls go to the Render API host.

## 6. Notes

- Render free instances can sleep after idle periods. Upgrade the plan if you want always-on behavior.
- The backend Docker image now respects `PORT`, which makes Render detection more reliable.
- The frontend build writes `env.js` from Vercel environment variables, so redeploy after changing frontend env values.
- `KAZIX_API_BASE`, `API_BASE_URL`, and `VITE_API_URL` are all accepted, but `KAZIX_API_BASE` is the canonical name in this repo.

## References

- Render Web Services: https://render.com/docs/web-services
- Render Health Checks: https://render.com/docs/health-checks
- Render Blueprint Spec: https://render.com/docs/blueprint-spec
- Vercel `vercel.json`: https://vercel.com/docs/project-configuration/vercel-json
