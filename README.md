# Fiscus

Personal finance app.

- **Phase 1 — Foundation**: Django project wired to Supabase Postgres, deployable to Vercel as serverless functions.
- **Phase 2 — Landing page**: brutalist design system + 3D hero (Three.js clock tower) + client-side Supabase auth.

## Phase 2: Brutalist landing page

- `core/templates/core/index.html` — landing template served at `/`: FISCUS wordmark, "Learn money by using it." tagline, 91% / 43% / 75%+ stat cards.
- `core/static/core/css/brutalist.css` — the design system: raw system-ui/monospace fonts, thick black borders, hard offset shadows (no blur), blue/white/black palette, no rounded corners, visible grid lines.
- `core/static/core/js/hero3d.js` — Three.js brutalist clock tower: unlit `MeshBasicMaterial` boxes + edge wireframes, slow auto-rotate, drag-to-orbit. Falls back to a static SVG poster on mobile, `prefers-reduced-motion`, or when WebGL is unavailable.
- `core/static/core/js/landing.js` — Supabase Auth JS (email/password signup, login, magic link) against the anon key injected by the view. Real keys required in `.env` / Vercel env vars for auth to work.
- `scripts/render_preview.py` — dev tool: renders the template into a standalone `preview.html` (gitignored) with CSS/JS inlined for serverless visual QA. `?force3d=1` forces the WebGL path on narrow viewports.

Stat numbers/labels are placeholders — swap in the deck's figures in `index.html`.

## Phase 3: Track module (expenses + budgets)

- `track/models.py` — `Category` (global reference data, seeded via migration), `Expense` (amount, category, type income/expense, date, note, user_id), `Budget` (category, monthly_limit, spent, user_id) with a unique per-user/category constraint. `user_id` is the Supabase auth uid (a UUID column, not a Django user).
- `track/auth.py` — `SupabaseJWTAuthentication`, a DRF auth backend that reads `Authorization: Bearer <jwt>`, verifies the RS256 signature against Supabase's JWKS (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, cached), checks `exp`/`aud`, and attaches a `SupabaseUser(id, email)` to the request.
- `track/views.py` — DRF viewsets: `GET/POST/PATCH/DELETE /api/expenses/` and `/api/budgets/`, public `GET /api/categories/`, and `GET /api/dashboard/` (spend by category, budget progress with over-budget flags, 6-month trend). Every expense mutation recomputes `Budget.spent` from the current month's expenses, so bars react live.
- `track/templates/track/dashboard.html` + `dashboard.js` — logged-in page at `/dashboard/`: add/edit/delete entries, budget bars (blue under budget, red over), Chart.js pie (spend by category) + bar (monthly trend). The browser sends the Supabase access token from the session; a 401 redirects to the landing auth form.
- `supabase/rls_policies.sql` + `scripts/apply_rls.py` — RLS policies so Expense/Budget rows are only visible to their owning user (defense in depth for direct PostgREST access; Django connects with the privileged postgres role and enforces ownership itself).

### Track module — setup (already done for the live project)

```bash
.venv/Scripts/python.exe manage.py migrate          # create tables in Supabase
.venv/Scripts/python.exe scripts/apply_rls.py        # enable RLS + policies
# tests — use a local DB so the runner doesn't touch Supabase
DATABASE_URL=sqlite:///test.db .venv/Scripts/python.exe manage.py test track learn

## Phase 4: Learn module (lessons + quizzes)

- `learn/models.py` — `Lesson` (title, content, `quiz_questions` JSONField, order/slug) and `QuizAttempt` (user_id, lesson, score, streak_count, badge — badge is reserved for Phase 5).
- `learn/management/commands/seed_lessons.py` — idempotent seed of the six lessons (Budgeting Basics → Reading a Portfolio), static content, DB-stored, no CMS.
- Pages: `/learn/` (list, with best-score ✓ marks + current streak when logged in) and `/learn/<slug>/` (lesson content + playable quiz).
- Quiz (`learn/static/learn/js/learn.js`): vanilla JS, instant per-question feedback with no page reload, question locking, auto-save on completion.
- `POST /api/lessons/<id>/attempt/` (Supabase JWT) — verifies answers, records a `QuizAttempt`, and returns score + the user's day-based streak (consecutive days with a completed quiz; same-day repeats don't inflate it). `GET /api/lessons/attempts/` returns best scores per lesson.
- `SupabaseJWTAuthentication` moved to `core/auth.py` so Track and Learn share it (track imports updated; 24 tests pass).

## Phase 5: Streaks, badges, auth polish, Invest stubs

- `streaks/models.py` — `Profile`: one int (`streak_count`) + one boolean per badge (7-Day Streak, Budget Keeper, First Trade, Course Complete). `record_activity()` drives the day-based streak (same-day no-op, next-day +1, gap resets to 1); `evaluate_badges()` recomputes booleans and returns newly unlocked names.
- `POST /api/cron/streaks/` — Vercel Cron endpoint (`vercel.json` crons, midnight UTC) that resets stale streaks; requires `CRON_SECRET` (`Authorization: Bearer`) in production.
- Badge unlocks: quiz completion (7-Day Streak, Course Complete), budget creation (Budget Keeper), holding creation (First Trade — via the stubbed Invest models). Unlocks are returned as `unlocked_badges` and toasted in the UI (brutalist toast cards + badge grid on the dashboard, streak shown live).
- Auth polish: Track/Learn pages now redirect to login without a session, dashboard API helper refreshes the Supabase session once on a 401 before redirecting, logout on every logged-in page.
- `invest/` — stub models only (`VirtualPortfolio`, `Holding`), migration applied to Supabase, **no UI** — Phase 6 builds on them.
- 38 tests pass (learn 12, track 12, streaks 14).

### Google sign-in (Supabase OAuth)

1. **Google Cloud Console** → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Web application):
   - **Authorized JavaScript origins:** `https://fiscus-one.vercel.app` (add `http://localhost:8765` for local dev)
   - **Authorized redirect URIs:** `https://yawvyibadiiacfstlkew.supabase.co/auth/v1/callback`
2. **Supabase** → Authentication → Providers → Google: enable, paste the Client ID + Client Secret.
3. Make sure **Authentication → URL Configuration → Site URL** is `https://fiscus-one.vercel.app`.

The landing page's "Sign in with Google" button calls `supabase.auth.signInWithOAuth({ provider: "google" })`; after the callback the session is active and the dashboard link appears.

### Production deploy checklist

1. Merge the Phase 4+5 branch into `main`; Vercel redeploys.
2. Vercel env vars (Settings → Environment Variables): `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=fiscus-one.vercel.app`, `CSRF_TRUSTED_ORIGINS=https://fiscus-one.vercel.app`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and **`CRON_SECRET`** (any strong random string — Vercel Cron sends it as `Authorization: Bearer`).
3. Cron: with `CRON_SECRET` set, the `vercel.json` cron (`0 0 * * *`) hits `/api/cron/streaks/` nightly to reset stale streaks.
4. Migrations already applied to Supabase (`track`, `learn`, `streaks`, `invest`); re-run `manage.py migrate` after deploy if models change.
5. Smoke the loop on the live URL: sign up → log an expense → do a lesson → watch the streak and badges panel update.
```

## Stack

- **Backend**: Django 6 (Python 3.12+), `fiscus/` project package + `core` app
- **Config**: `django-environ` — all secrets via env vars, never in the repo
- **Database**: Supabase Postgres via `DATABASE_URL` (psycopg2)
- **Static files**: WhiteNoise (served by Django itself — no CDN/static host needed)
- **Deploy**: Vercel serverless (`vercel.json` + `build_files.sh`, `@vercel/python` WSGI runtime)

## Project structure

```
fiscus/            Django project package (settings, urls, wsgi/asgi)
core/              Core Django app (landing page)
manage.py          Django CLI entrypoint
vercel.json        Vercel serverless build/routes config
build_files.sh     Vercel build: pip install + collectstatic
.env.example       Documented env template (copy → .env)
.env               Local secrets — GITIGNORED, never commit
```

## Local setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt # macOS/Linux

cp .env.example .env   # then fill in real values
.venv/Scripts/python.exe manage.py runserver
```

### Environment variables

| Variable | Where from | Required |
|---|---|---|
| `DJANGO_SECRET_KEY` | Generate (`secrets.token_urlsafe(50)`) | yes |
| `DEBUG` | `True` locally, `False` in prod | yes |
| `ALLOWED_HOSTS` | Comma-separated hosts (`*` for dev) | yes |
| `DATABASE_URL` | Supabase → Project Settings → Database → Connection string (URI) | yes |
| `SUPABASE_URL` | Supabase → Project Settings → API | later phases |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API | later phases |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API (keep secret!) | later phases |

## Deploying to Vercel

1. Push the repo to GitHub (this branch).
2. In [vercel.com](https://vercel.com) → **Add New Project** → import the GitHub repo.
   - Framework preset: **Other** (build is driven by `vercel.json` / `build_files.sh`).
3. Add the same env vars as in `.env` (at minimum `DATABASE_URL`, `DEBUG=False`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS=<your-vercel-domain>`) under **Settings → Environment Variables**.
4. Deploy. `build_files.sh` installs deps + runs `collectstatic`; `fiscus/wsgi.py` is served via `@vercel/python`.
5. Hit the generated `*.vercel.app` URL — you should see the "It works!" page.

> **Note**: `DEBUG=False` + `ALLOWED_HOSTS=*` is a security warning in production; set `ALLOWED_HOSTS` to your actual Vercel domain once you have it.

## Supabase notes

- Use the **Transaction pooler** URI (port `6543`) — designed for serverless connections; the direct connection (port `5432`) can be exhausted by many short-lived serverless functions.
- `python manage.py migrate` from your machine will create Django's auth/session/admin tables in Supabase. Keep migrations out of the serverless build — run them manually before/after deploys.
