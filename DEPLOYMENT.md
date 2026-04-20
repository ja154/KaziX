# KaziX Deployment Guide: Vercel + Fly.io

**Status**: Phase 1 Complete ✅ | Ready for Phase 2-6

This guide walks through deploying KaziX to **Vercel (Frontend) + Fly.io (Backend)** with Supabase as the database.

---

## 📋 Prerequisites

### Accounts & Tools Required
- [ ] **GitHub**: Repository pushed to GitHub (public or private)
- [ ] **Vercel Account**: https://vercel.com (free, supports GitHub OAuth)
- [ ] **Fly.io Account**: https://fly.io (free tier available)
- [ ] **Supabase Account**: https://supabase.com (already using: `https://your-project.supabase.co`)
- [ ] **Flyctl CLI**: Local machine (for Fly.io deployment)
  ```bash
  curl -L https://fly.io/install.sh | sh
  ```

### What's Already Done ✅
- ✅ `backend/Dockerfile` — Multi-stage Alpine build for minimal image size
- ✅ `backend/.dockerignore` — Excludes `.env`, cache, unnecessary files
- ✅ `backend/.env.example` — Complete environment variable documentation
- ✅ `frontend/.env.example` — Supabase configuration template

---

## 🚀 Phase 2: Backend Deployment to Fly.io

### 2.1 Install Flyctl CLI
```bash
# macOS
brew install flyctl

# Linux (or use curl script above)
curl -L https://fly.io/install.sh | sh

# Verify installation
flyctl version
```

### 2.2 Authenticate with Fly.io
```bash
flyctl auth login
# Opens browser → Sign up or log in with GitHub
# Returns auth token locally
```

### 2.3 Create `.env` from `.env.example`
```bash
cd backend
cp .env.example .env
```

**Fill in the `.env` file** with:
- `APP_ENV=production` (for deployment)
- `APP_SECRET_KEY=` Generate via: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Supabase credentials from your project dashboard
- M-Pesa sandbox credentials (or leave empty for now)
- Africa's Talking sandbox API key (or leave empty for now)

### 2.4 Launch Fly.io App (Auto-generates `fly.toml`)
```bash
flyctl launch
```

This will prompt:
```
✓ Detected Python app
? App name: kazix-api              # Name your backend app (e.g., kazix-api)
? Select region: [jnb] [lhr]       # Choose: jnb (Johannesburg, recommended for Africa)
? Would you like to set up a Postgres database? (y/N): n  # No, using Supabase
? Would you like to set up an upstash redis? (y/N): n     # No, not needed
```

**Output**: Creates `backend/fly.toml` with deployment config.

### 2.5 Update `fly.toml` with Environment Variables

Edit `backend/fly.toml` and add this section (after `[env]`):
```toml
[env]
APP_ENV = "production"
APP_HOST = "0.0.0.0"
APP_PORT = "8000"
ALLOWED_ORIGINS = "https://kazix.vercel.app,http://localhost:3000"
LOG_LEVEL = "INFO"
MPESA_CALLBACK_URL = "https://kazix-api.fly.dev/v1/mpesa/callback"
AT_SENDER_ID = "KaziX"
AT_USERNAME = "sandbox"
MPESA_ENV = "sandbox"
MPESA_SHORTCODE = "174379"
OTP_MAX_RETRIES = "3"
OTP_INITIAL_BACKOFF_MS = "100"
OTP_MAX_BACKOFF_MS = "5000"
OTP_BACKOFF_MULTIPLIER = "2.0"
OTP_JITTER_ENABLED = "true"

[http_service]
internal_port = 8000
force_https = true
auto_stop_machines = true
auto_start_machines = true
min_machines_running = 2
```

**Note**: Replace `kazix-api.fly.dev` with your actual Fly.io app name.

### 2.6 Set Production Secrets via Flyctl

Upload sensitive variables (never stored in `fly.toml`):
```bash
# Commands to run from backend/ directory
flyctl secrets set APP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
flyctl secrets set SUPABASE_URL="https://your-project.supabase.co"
flyctl secrets set SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
flyctl secrets set SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
flyctl secrets set SUPABASE_JWT_SECRET="your-jwt-secret-here"

# Optional: Payment provider credentials (leave empty for sandbox mode)
flyctl secrets set MPESA_CONSUMER_KEY=""
flyctl secrets set MPESA_CONSUMER_SECRET=""
flyctl secrets set MPESA_PASSKEY=""
flyctl secrets set AT_API_KEY=""
```

Check secrets were set:
```bash
flyctl secrets list
```

### 2.7 Deploy to Fly.io
```bash
flyctl deploy
```

**Output**:
```
✓ Pushed image to registry
✓ Released v1
✓ Instances become healthy
✓ App running on https://kazix-api.fly.dev
```

### 2.8 Verify Backend Health
```bash
# From terminal
curl https://kazix-api.fly.dev/health

# Or visit in browser (replace with your app name)
https://kazix-api.fly.dev/docs
```

Should return: `{"status": "ok"}` (or show FastAPI Swagger UI).

Monitor logs:
```bash
flyctl logs
```

---

## 🎨 Phase 3: Frontend Deployment to Vercel

### 3.1 Push Code to GitHub
```bash
cd /home/jay/Desktop/KaziX
git add .
git commit -m "Add Dockerfile, .env.example, deployment configuration"
git push origin main
```

### 3.2 Create Vercel Account & Connect GitHub
1. Go to https://vercel.com/new
2. Sign up with GitHub
3. Authorize Vercel to access your repositories
4. Select your **KaziX** repository

### 3.3 Configure Vercel Project Settings
1. Click **Import Project** → Select your KaziX repo
2. Under **Configure Project**:
   - **Framework Preset**: None (static HTML/CSS/JS)
   - **Root Directory**: `frontend` ✅
   - **Build Command**: Leave empty (no build step needed)
   - **Output Directory**: Leave empty

3. Click **Environment Variables** (or go to **Project Settings** → **Environment Variables**)
   - Add variable: `VITE_SUPABASE_URL` = `https://your-project.supabase.co`
   - Add variable: `VITE_SUPABASE_ANON_KEY` = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
   - Add variable: `SUPABASE_REDIRECT_URL` = `https://kazix.vercel.app` (or your custom domain)
   - Add variable: `VITE_API_URL` = `https://kazix-api.fly.dev` (your Fly.io backend URL)

4. Click **Deploy**

**Output**: Frontend deployed to `https://kazix.vercel.app` (or your custom domain).

### 3.4 Verify Frontend Loads
Visit: https://kazix.vercel.app

Should see KaziX landing page (no console errors).

---

## 🔗 Phase 4: CORS & Integration Configuration

### 4.1 Update Backend CORS Configuration

Edit [backend/app/main.py](backend/app/main.py) around line 100:
```python
# Find this section and update ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Uses ALLOWED_ORIGINS from .env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
    max_age=86400,
)
```

Ensure your `fly.toml` has (from Phase 2.5):
```
ALLOWED_ORIGINS = "https://kazix.vercel.app,http://localhost:3000"
```

Then redeploy:
```bash
flyctl deploy
```

### 4.2 Update Backend Callback URLs

M-Pesa, Africa's Talking, and other third-party services need valid callback URLs:

In `fly.toml` [env], update:
```toml
MPESA_CALLBACK_URL = "https://kazix-api.fly.dev/v1/mpesa/callback"  # Replace with your Fly.io URL
```

### 4.3 Configure Custom Domain (Optional)

If using `api.kazix.co.ke` instead of `kazix-api.fly.dev`:

**For Fly.io backend:**
```bash
flyctl certs create api.kazix.co.ke
# Returns DNS records to add to your domain registrar
# Once DNS propagates, Fly.io auto-generates SSL cert
```

**For Vercel frontend:**
1. Go to Vercel Dashboard → Project → **Domains**
2. Add your domain (e.g., `kazix.co.ke`)
3. Update DNS records as instructed by Vercel

---

## 🗄️ Phase 5: Database & Secrets

### 5.1 Verify Supabase Connection
```bash
# Test from local machine
curl -X GET "https://your-project.supabase.co/rest/v1/profiles?select=id,phone" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Should return profiles (or empty array if no data).

### 5.2 Run Database Migrations (If Needed)
If migrations haven't been applied:
```bash
cd backend/supabase
# Use Supabase CLI to push migrations (already in repo)
supabase db push
```

### 5.3 Verify Secrets Are Set
```bash
flyctl secrets list
# Should show all secrets set in Phase 2.6
```

### 5.4 Rotate Secrets (Security Best Practice)
**Never** reuse dummy/test secrets in production.

Generate new production secrets:
```bash
# Generate new APP_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update in Fly.io
flyctl secrets set APP_SECRET_KEY="<new-value>"

# Verify change (requires re-deploy)
flyctl deploy
```

---

## ✅ Phase 6: Testing & Monitoring

### 6.1 Smoke Tests

#### Backend Health Check
```bash
curl https://kazix-api.fly.dev/health
# Expected: {"status": "ok"}

# Or check API docs
open https://kazix-api.fly.dev/docs
```

#### Frontend Loads
```bash
open https://kazix.vercel.app
# Should show landing page, no console errors
```

#### CORS Configuration
1. Open browser DevTools (F12)
2. Navigate to a form on the frontend (e.g., login page)
3. Check **Network** tab
4. Submit form → verify API call succeeds (no `CORS error`)

#### End-to-End Auth
1. Click **Login** on frontend
2. Enter test phone number (e.g., +254XXXXXXXXX)
3. Request OTP
4. Verify in `flyctl logs` that backend processed OTP
5. Submit code and verify login succeeds

### 6.2 Monitor Backend Logs
```bash
# Real-time logs
flyctl logs

# Search for errors
flyctl logs --grep error

# View specific instance
flyctl status
```

### 6.3 Monitor Vercel Build & Deployment
1. Go to Vercel Dashboard → KaziX project → **Deployments**
2. View build logs, deployment status
3. Check for any errors during environment variable injection

### 6.4 Test CORS Headers
```bash
# Check security headers
curl -I https://kazix-api.fly.dev/health
# Should include:
# x-content-type-options: nosniff
# x-frame-options: DENY
# strict-transport-security: max-age=31536000

# Check CORS headers
curl -I \
  -H "Origin: https://kazix.vercel.app" \
  https://kazix-api.fly.dev/health
# Should include:
# access-control-allow-origin: https://kazix.vercel.app
```

### 6.5 Load Testing (Optional)
Test free tier performance:
```bash
# Install Apache Bench (if not present)
brew install httpd  # or apt install apache2-utils

# Simple load test (50 requests, 10 concurrent)
ab -n 50 -c 10 https://kazix-api.fly.dev/health
```

Monitor during test:
```bash
flyctl status
# Watch CPU%, Memory, instance health
```

### 6.6 Set Up Error Tracking (Optional)
Enable Sentry for production errors:

1. Create Sentry account: https://sentry.io/
2. Create a new Python project
3. Get DSN: `https://xxxxx@xxxxx.ingest.sentry.io/xxxxx`
4. Set secret in Fly.io:
   ```bash
   flyctl secrets set SENTRY_DSN="https://xxxxx@xxxxx.ingest.sentry.io/xxxxx"
   flyctl deploy
   ```

---

## 🔍 Troubleshooting

### "CORS error in frontend logs"
**Problem**: Frontend → Backend API calls blocked by browser
**Solution**:
1. Check `ALLOWED_ORIGINS` in `fly.toml` includes Vercel domain
2. Verify frontend is NOT sending cookies on CORS requests (should use JWT)
3. Check backend CORS middleware in `app/main.py`
4. Redeploy: `flyctl deploy`

### "Backend health check fails"
**Problem**: `https://kazix-api.fly.dev/health` returns error
**Solution**:
1. Check Fly.io logs: `flyctl logs | grep error`
2. Verify environment variables set: `flyctl secrets list`
3. Verify Supabase credentials are valid
4. Check Docker image built correctly: `flyctl log`

### "Frontend shows wrong API URL"
**Problem**: Frontend calling localhost instead of Fly.io backend
**Solution**:
1. Frontend env vars are baked in at BUILD TIME (not runtime)
2. Update `VITE_API_URL` in Vercel Project Settings
3. Trigger rebuild: **Vercel Dashboard** → **Projects** → **KaziX** → **Deployments** → **Redeploy**

### "Health check still failing (docker/fly issue)"
**Problem**: Container starts but health check times out
**Solution**:
1. The Dockerfile includes `HEALTHCHECK` that requires `requests` library
2. This is installed in `requirements.txt` ✅
3. If still failing, simplify health check in `fly.toml`:
   ```toml
   [http_service]
   internal_port = 8000
   # Remove or disable health check temporarily
   # grace_period = "10s"
   # initial_delay = "5s"
   ```

---

## 📊 Cost Analysis (As of April 2026)

| Component | Cost | Notes |
|-----------|------|-------|
| Vercel Frontend | **$0/month** | Free tier includes 100GB bandwidth |
| Fly.io Backend | **$0-5/month** | Free tier: shared CPU 256MB × 3 instances. Pay if >400GB data transfer or need more CPU |
| Supabase Database | ~**$10-25/month** | Depends on storage & bandwidth (shared with other projects) |
| **Total** | ~**$10-30/month** | Way cheaper than AWS/GCP; upgrade only if hitting free tier limits |

---

## 🎯 Post-Deployment Checklist

- [ ] Backend health check responds: `https://kazix-api.fly.dev/health`
- [ ] Frontend loads without console errors: `https://kazix.vercel.app`
- [ ] CORS requests from frontend succeed (check DevTools Network)
- [ ] Auth flow works (login → OTP → token)
- [ ] Database queries work (`GET /profiles` returns data)
- [ ] M-Pesa callback URL is valid (in `MPESA_CALLBACK_URL`)
- [ ] Africa's Talking SMS can be sent (test OTP)
- [ ] Backend logs are clean (no persistent errors)
- [ ] Vercel & Fly.io dashboards show green (healthy)
- [ ] Custom domain (if applicable) resolves to correct IP
- [ ] SSL/TLS certificates are valid (green lock in browser)

---

## 📞 Support & Resources

- **Fly.io Docs**: https://fly.io/docs/
- **Vercel Docs**: https://vercel.com/docs
- **Supabase Docs**: https://supabase.com/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Docker Docs**: https://docs.docker.com/

---

## ⚠️ Production Security Considerations

1. **Never commit `.env` files** — Add to `.gitignore`
2. **Rotate secrets regularly** — Use `flyctl secrets set` to update
3. **Enable HTTPS only** — Fly.io auto-handles via Let's Encrypt
4. **Restrict CORS origins** — Don't use wildcard `*` in production
5. **Monitor logs weekly** — Check `flyctl logs` for errors/attacks
6. **Enable error tracking** — Sentry (or similar) for alerts
7. **Database backups** — Supabase handles automatic daily backups
8. **Rate limiting enabled** — FastAPI has slowapi middleware enabled

---

**Last Updated**: April 20, 2026 | Deployment Status: Phase 1 ✅ | Verified: Dockerfile, .dockerignore, .env.example files created
