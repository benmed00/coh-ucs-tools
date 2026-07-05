# Deployment guide

CoH UCS Tools ships as a **Docker** image (FastAPI + static SPA + SQLite on a persistent volume).

## Quick start (local)

```powershell
docker compose up --build
# → http://127.0.0.1:8000
# → Swagger: http://127.0.0.1:8000/docs
```

## Fly.io (recommended free host)

**Why Fly.io:** Docker-native, **persistent volume** for SQLite + uploads, GitHub deploy, EU region (`cdg` = Paris).

### Prerequisites

1. [Fly.io account](https://fly.io/) (GitHub sign-in works).
2. [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed.
3. This repo cloned / pushed to GitHub.

### One-time setup

```powershell
# Install flyctl (Windows)
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
$env:Path += ";$env:USERPROFILE\.fly\bin"

# Log in (opens browser once)
fly auth login

# Create the app (name must be globally unique — edit fly.toml if taken)
fly apps create coh-ucs-tools-benmed00

# Persistent disk (1 GB) — same region as fly.toml primary_region
fly volumes create coh_data --region cdg --size 1 -a coh-ucs-tools-benmed00

# Optional API key (recommended for public deploy)
fly secrets set UCS_API_KEY="change-me-to-a-long-random-string" -a coh-ucs-tools-benmed00

# Optional DeepL for MT lab
# fly secrets set DEEPL_API_KEY="..." -a coh-ucs-tools-benmed00
```

### Deploy

```powershell
fly deploy -a coh-ucs-tools-benmed00
```

Your app will be at: **https://coh-ucs-tools-benmed00.fly.dev**

```powershell
fly open -a coh-ucs-tools-benmed00
fly logs -a coh-ucs-tools-benmed00
fly status -a coh-ucs-tools-benmed00
```

### Free tier notes

| Setting | Value | Why |
|---------|-------|-----|
| `memory` | 256mb | Fits Fly free allowance |
| `auto_stop_machines` | `off` | Avoid 30s+ cold starts on demo |
| Volume | 1 GB at `/data` | SQLite + user uploads survive restarts |

If the app OOMs on large UCS uploads, bump to `512mb` (may exceed free tier).

### GitHub Actions (CI deploy)

1. Create a deploy token: `fly tokens create deploy -a coh-ucs-tools-benmed00`
2. Add repo secret **`FLY_API_TOKEN`** in GitHub → Settings → Secrets.
3. Push to `master` — workflow `.github/workflows/fly-deploy.yml` deploys automatically.

### What NOT to put on the server

- Copyrighted game `.ucs` files (NSV English, complete union, etc.)
- `downloads/mt_cache.json` or other translation caches

Users upload their own files; built-in “versions” only register when paths exist on the host (empty on Fly — that is expected).

---

## Oracle Cloud Always Free (alternative)

For a always-on VM with more RAM and no cold starts:

1. Create an **Ampere A1** Ubuntu VM (Always Free).
2. Install Docker: `curl -fsSL https://get.docker.com | sh`
3. Clone repo, `docker compose up -d`
4. Point a domain at the VM IP; use **Caddy** or **nginx** for HTTPS.

---

## Render (demo only)

Free Render web services have **ephemeral disk** — SQLite and uploads are lost on restart. Use only for a quick demo, or attach a paid persistent disk / external Postgres.

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SQLITE_PATH` | `webapp/data/app.db` | SQLite database |
| `UCS_WEBAPP_UPLOADS` | `uploads/` | UCS byte storage |
| `UCS_API_KEY` | (none) | Require `X-API-Key` header when set |
| `CORS_ORIGINS` | (see below) | Comma-separated extra allowed browser origins |
| `DEEPL_API_KEY` | (none) | DeepL backend for MT lab |
| `REDIS_URL` | (none) | Documented stub; in-memory rate limit fallback |

---

## Health check

```http
GET /api/health
```

Returns `{"status":"ok", ...}` — used by Fly.io and Docker orchestrators.

---

## Hybrid deployment (Phase 1)

Split the **static UI** (CDN) from the **API** (Fly.io). The SPA calls
`https://coh-ucs-tools.fly.dev` via `window.API_BASE` in `js/config.js`;
locally `API_BASE` is empty so the monolith keeps working.

| Layer | Host | URL |
|-------|------|-----|
| API | Fly.io | https://coh-ucs-tools.fly.dev |
| UI (GitHub Pages) | GitHub Actions | https://benmed00.github.io/coh-ucs-tools/ |
| UI (Cloudflare Pages, optional) | Cloudflare | https://coh-ucs-tools.pages.dev (custom domain possible) |

### Build static frontend

```powershell
python scripts/build_static.py
# → dist/index.html, dist/css/, dist/js/config.js (production API_BASE), …
```

Options:

- `--api-base https://coh-ucs-tools.fly.dev` — API origin (default)
- `--out dist` — output directory

Serve locally to preview:

```powershell
python scripts/build_static.py
cd dist
python -m http.server 8080
# → http://127.0.0.1:8080/  (UI talks to Fly.io API)
```

### GitHub Pages (automated)

1. **Enable Pages:** repo **Settings → Pages → Build and deployment → Source:**
   choose **GitHub Actions** (not “Deploy from a branch”).
2. Push to `master` — workflow `.github/workflows/pages.yml` runs
   `python scripts/build_static.py` and publishes `dist/`.
3. API deploy is unchanged: `.github/workflows/fly-deploy.yml` (Fly.io only).

### Cloudflare Pages (optional)

Connect the same repo in Cloudflare Pages:

| Setting | Value |
|---------|-------|
| Build command | `python scripts/build_static.py` |
| Build output directory | `dist` |
| Root directory | `/` (repo root) |

No Node.js required — the build script is stdlib-only Python.

### CORS

The Fly.io API allows browser requests from:

- `https://coh-ucs-tools.fly.dev` (same-origin / API docs)
- `https://coh-ucs-tools.pages.dev` (Cloudflare Pages default)
- `https://benmed00.github.io` (GitHub Pages)
- `http://127.0.0.1:8000`, `http://localhost:8000` (local monolith)

Add custom UI domains with Fly secret or env:

```powershell
fly secrets set CORS_ORIGINS="https://my-ui.example.com" -a coh-ucs-tools
```

(`CORS_ORIGINS` is merged with the defaults above.)

Credentials and headers: `X-API-Key`, `Content-Type` are allowed for API key auth.

### What stays on Fly.io

- REST API, SQLite, uploads volume, rate limiting, optional `UCS_API_KEY`
- OpenAPI at `/docs`, `/redoc`

The static CDN serves only HTML/CSS/JS — no server-side state.

---
