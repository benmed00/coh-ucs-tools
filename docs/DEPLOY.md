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
fly apps create coh-ucs-tools

# Persistent disk (1 GB) — same region as fly.toml primary_region (iad)
fly volumes create coh_data --region iad --size 1 -a coh-ucs-tools

# Optional API key (recommended for public deploy)
fly secrets set UCS_API_KEY="change-me-to-a-long-random-string" -a coh-ucs-tools

# Optional DeepL for MT lab
# fly secrets set DEEPL_API_KEY="..." -a coh-ucs-tools
```

### Deploy

```powershell
fly deploy -a coh-ucs-tools
```

Your app will be at: **https://coh-ucs-tools.fly.dev**

```powershell
fly open -a coh-ucs-tools
fly logs -a coh-ucs-tools
fly status -a coh-ucs-tools
```

### Free tier notes

| Setting | Value | Why |
|---------|-------|-----|
| `memory` | 256mb | Fits Fly free allowance |
| `auto_stop_machines` | `off` | Avoid 30s+ cold starts on demo |
| Volume | 1 GB at `/data` | SQLite + user uploads survive restarts |

If the app OOMs on large UCS uploads, bump to `512mb` (may exceed free tier).

### GitHub Actions (CI deploy)

**Workflow order:** push to `master` runs **Tests** (unit matrix + Playwright E2E) and **GitHub Pages** in parallel. **Fly Deploy** runs only after **Tests** succeeds (`workflow_run`), with a pre-deploy import smoke check.

| Workflow | File | Trigger |
|----------|------|---------|
| Tests | `.github/workflows/test.yml` | push / PR |
| Fly Deploy | `.github/workflows/fly-deploy.yml` | after Tests success, or manual |
| GitHub Pages | `.github/workflows/pages.yml` | push / manual |

1. Create a deploy token: `fly tokens create deploy -a coh-ucs-tools`
2. Add repo secret **`FLY_API_TOKEN`** in GitHub → Settings → Secrets → Actions:

   ```powershell
   gh secret set FLY_API_TOKEN --body "PASTE_FlyV1_TOKEN"
   ```

3. Push to `master` — Fly Deploy runs after Tests pass and executes a **CORS smoke test** (`Origin: https://benmed00.github.io`).

**Rotate `FLY_API_TOKEN` when expired** (Fly Deploy fails with `Error: unauthorized`):

```powershell
fly auth login
fly tokens create deploy -a coh-ucs-tools -n "github-actions" -x 8760h
gh secret set FLY_API_TOKEN --body "PASTE_NEW_TOKEN"
```

If the web UI blocks personal tokens (SSO org), use `fly tokens create deploy` via CLI — not Account → Access Tokens.

**Avoid concurrent deploys:** do not run local `fly deploy` while the **Fly Deploy** GitHub Action is in progress (VM lease conflicts). The workflow uses `concurrency: deploy-group`.

**GitHub Pages dual workflow:** the repo uses [pages.yml](.github/workflows/pages.yml) (`deploy-pages@v4`). GitHub may also show a dynamic `pages-build-deployment` run — if the custom **GitHub Pages** workflow succeeded, ignore transient failures on the dynamic one. Settings → Pages → Source must be **GitHub Actions** only.

### Retire duplicate Fly apps

If you created an earlier trial app (e.g. `coh-ucs-tools-benmed00`), remove it after migrating to `coh-ucs-tools`:

```powershell
fly apps destroy coh-ucs-tools-benmed00 --yes
```

### What NOT to put on the server

- Copyrighted game `.ucs` files (NSV English, complete union, etc.)
- `downloads/mt_cache.json` or other translation caches

Users upload their own files; built-in “versions” only register when paths exist on the host (empty on Fly — that is expected). The dashboard shows a banner in hybrid mode when no version files are on disk.

**Hybrid auth:** GitHub Pages UI + Fly API uses **`X-API-Key`** (Settings) for protected mutations. Cookie/OAuth sessions require the monolith (same origin). The SPA omits `credentials: "include"` on cross-origin fetches.

**Rate limits:** Per-IP limits apply on public API endpoints (stricter on uploads). Tune via `webapp/rate_limit.py` or set `REDIS_URL` for shared state.

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

### Troubleshooting GitHub Pages

| Symptom | Cause | Fix |
|---------|-------|-----|
| Site shows **README markdown** instead of the dark UI | Source was **Deploy from a branch** (`master` / root) | Settings → Pages → Source: **GitHub Actions**. Or run `gh api repos/OWNER/REPO/pages -X PUT -f build_type=workflow` |
| Red banner: custom domain **not properly formatted** | Invalid name like `company_of_heroes_translations` (no `.com`, underscores) | Leave **Custom domain** empty, or use a real FQDN e.g. `coh.example.com` and add DNS CNAME → `benmed00.github.io` |
| Actions workflow **404** on deploy | Pages not set to GitHub Actions yet | Enable as above, then re-run **GitHub Pages** workflow |
| Upload/merge returns **401** on the live UI | `UCS_API_KEY` set on Fly | Settings → paste API key (stored in browser `localStorage`) |
| **Failed to fetch** / CORS blocked from `benmed00.github.io` | Fly API still on an **old image** (CI deploy failed) or missing CORS headers on error responses | See [CORS / Fly deploy](#cors--fly-deploy) below |

After switching to GitHub Actions, wait ~1 minute and hard-refresh
`https://benmed00.github.io/coh-ucs-tools/` — you should see **“UCS LOCALIZATION COMMAND CONSOLE”**, not the README.

### CORS / Fly deploy

The GitHub Pages UI (`https://benmed00.github.io`) calls the Fly API cross-origin. The API must be deployed with `CORSMiddleware` allowing that origin.

**Verify the live API:**

```powershell
curl.exe -s -D - -o NUL -H "Origin: https://benmed00.github.io" https://coh-ucs-tools.fly.dev/api/versions
```

You should see `Access-Control-Allow-Origin: https://benmed00.github.io`. If the header is missing, redeploy:

1. Create a Fly deploy token: [fly.io/user/personal_access_tokens](https://fly.io/user/personal_access_tokens) → **Deploy tokens** → app `coh-ucs-tools`.
2. GitHub → repo **Settings → Secrets → Actions** → update **`FLY_API_TOKEN`**.
3. **Actions → Fly Deploy → Run workflow** (or push to `master`).

Recent failed runs show `Error: unauthorized` — the secret is expired or wrong. Until deploy succeeds, the Pages UI will show **Failed to fetch**.

---

## SEO & search indexing (Phase 3)

The UI is optimized for search engines: path-based URLs, injected metadata from
`webapp/seo.py`, `/about` landing page with FAQ schema, `sitemap.xml`, and
`robots.txt`.

### Submit sitemaps

| Property | Sitemap URL |
|----------|-------------|
| **Google Search Console** (UI) | `https://benmed00.github.io/coh-ucs-tools/sitemap.xml` |
| **Bing Webmaster Tools** (UI) | same |
| **Fly.io** (API docs, optional) | `https://coh-ucs-tools.fly.dev/sitemap.xml` |

**Google:** [Search Console](https://search.google.com/search-console) → add property
`https://benmed00.github.io/coh-ucs-tools/` → Sitemaps → paste the sitemap URL.

**Bing:** [Webmaster Tools](https://www.bing.com/webmasters) → add site → Sitemaps.

Target queries to monitor: *Company of Heroes localization*, *UCS file tool*,
*CoH modding UCS*, *RelicCOH English ucs*.

### Site verification meta tags

Google Search Console verification is **built in** for the GitHub Pages UI:

| Method | URL / location |
|--------|----------------|
| **HTML file** (recommended) | `https://benmed00.github.io/coh-ucs-tools/google34239ced659ea41b.html` |
| **Meta tag** | Injected in `<head>` on every page (also works after deploy) |

After pushing to `master`, wait for the GitHub Pages workflow, then click **Valider** in Search Console using either method.

To override the meta tag token (e.g. if Google rotates it):

```powershell
fly secrets set UCS_GOOGLE_SITE_VERIFICATION="your-new-token" -a coh-ucs-tools
```

For Bing Webmaster Tools:

```powershell
fly secrets set UCS_BING_SITE_VERIFICATION="your-bing-token" -a coh-ucs-tools
```

Redeploy Fly after setting secrets (meta injection on the monolith). GitHub Pages picks up the committed verification file and default meta tag on the next Pages deploy.

### Performance notes

- **Chart.js** loads only when you open Compare or Languages (lazy).
- **Fonts** are self-hosted WOFF2 (Inter, IBM Plex Mono, Allerta Stencil) — no Google Fonts request.

---

## SEO polish (Phase 4)

Phase 4 adds performance and crawl-signal improvements on top of Phase 3.

### Self-hosted fonts

Fonts live under `webapp/static/fonts/` with `@font-face` rules in
`webapp/static/css/fonts.css`. Regenerate after a Google Fonts update:

```powershell
python scripts/download_fonts.py
```

Commit the WOFF2 files and updated `fonts.css` before deploying.

### Structured data

The homepage injects a JSON-LD `@graph` with:

| Schema | Purpose |
|--------|---------|
| `WebApplication` | App features, license, repo |
| `WebSite` + `SearchAction` | Site search (`/search?q=…`) |
| `Organization` | Brand + GitHub link |

Each SPA route (except dashboard) gets a runtime `BreadcrumbList` via
`seo.js`. `/about` also injects `FAQPage` schema.

### Sitemap `lastmod`

`sitemap.xml` uses the date of the latest git commit touching `webapp/`.
If git is unavailable, it falls back to today's date.

### API indexing

All `/api/*` responses include `X-Robots-Tag: noindex, nofollow` so upload
and merge endpoints are not indexed as pages.

### IndexNow (optional)

For faster Bing/Yandex re-crawl after deploys:

1. Generate a key (8–128 hex chars), e.g. `openssl rand -hex 16`
2. Set it at build time or on Fly:

```powershell
$env:UCS_INDEXNOW_KEY = "your-key-here"
python scripts/build_static.py
```

Or on Fly:

```powershell
fly secrets set UCS_INDEXNOW_KEY="your-key-here" -a coh-ucs-tools
```

3. Verify the key file is reachable:
   `https://benmed00.github.io/coh-ucs-tools/{key}.txt`
4. After deploy, POST changed URLs to [IndexNow](https://www.indexnow.org/documentation)

### CDN cache headers

Static builds emit `_headers` for Cloudflare Pages (long cache on fonts,
shorter on sitemap/robots). Fly.io sets similar `Cache-Control` via middleware.

---
