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
