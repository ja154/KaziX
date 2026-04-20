# KaziX — Hire Trusted Fundis in Kenya

KaziX is a modern marketplace designed to connect skilled Kenyan workers (fundis) with clients. The platform prioritizes security and trust through built-in M-Pesa escrow payments, ID verification, and a transparent review system.

## 🌟 Key Features

### For Clients
- **Find Verified Fundis:** Browse through plumbers, electricians, painters, and more, all with verified IDs.
- **Secure Escrow:** Payments are held in escrow via M-Pesa and only released once the job is confirmed complete.
- **Fast Hiring:** Average response time of under 8 minutes.
- **Real Reviews:** Make informed decisions based on feedback from previous clients.

### For Pros (Fundis)
- **SMS Job Alerts:** Receive notifications for jobs in your area the moment they are posted.
- **Instant Payments:** Get paid directly to M-Pesa within minutes of job completion.
- **Reputation Building:** Grow your business with a verified profile and positive ratings.
- **Payment Guarantee:** Work with confidence knowing the client's funds are secured in escrow before you start.

## 🛠️ Tech Stack

- **Frontend:** HTML5, CSS3 (Vanilla CSS with modern features like CSS Variables, Grid, and Flexbox).
- **Typography:** 
  - `Syne`: For high-impact headings and branding.
  - `DM Sans`: For clean, readable body text.
- **Design Aesthetic:** High-contrast "Modern Brutalist" style with a focus on usability and accessibility.

## 📁 Project Structure

```text
KaziX/
├── frontend/
│   ├── pages/
│   │   ├── index.html              # Landing page
│   │   ├── client-dashboard.html   # Dashboard for clients to manage jobs
│   │   ├── worker-dashboard.html   # Dashboard for workers (Fundis)
│   │   └── ...                     # All frontend HTML pages
│   └── assets/
│       ├── css/
│       │   ├── styles.css          # Global styles and design tokens
│       │   └── admin.css
│       └── js/
│           ├── mobile-nav.js
│           ├── admin-shell.js
│           └── admin-disputes.js
├── backend/                    # FastAPI app and API
└── README.md
```

## 🚀 Getting Started

KaziX now runs from a single FastAPI backend that serves both the API and the frontend pages.

```bash
# Clone the repository
git clone https://github.com/your-username/kazix.git

# Navigate to the directory
cd kazix/backend

# Install dependencies if needed
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start the full site + API
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` for the website and `http://localhost:8000/docs` for API docs in development.

## OAuth Setup

Social login returns to `frontend/pages/auth-callback.html`, and Supabase must be allowed to send users back to that page.

- Supabase Auth redirect URLs should include `http://localhost:8000/pages/auth-callback.html` for local development.
- Google OAuth must authorize the Supabase callback URL, not the frontend page URL. For this project, that callback is `https://tziamornnxxsfofzyvpj.supabase.co/auth/v1/callback`.
- Google OAuth should also allow the local JavaScript origin `http://localhost:8000` while developing.

Reference docs:
- https://supabase.com/docs/guides/auth/social-login/auth-google
- https://supabase.com/docs/guides/auth/redirect-urls

## 🇰🇪 Built for Kenya
KaziX is designed with the local context in mind, focusing on mobile-first accessibility and deep integration with M-Pesa workflows.
