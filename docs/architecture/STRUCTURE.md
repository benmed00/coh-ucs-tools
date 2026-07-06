# Repository structure

Enterprise layout for **CoH UCS Tools**. Application behavior is unchanged; paths and folders are centralized for maintainability.

## Root layout

```
coh-ucs-tools/
├── src/coh_ucs_tools/     # Python package (src layout)
├── tests/                 # unit, api, static, fixtures
├── docs/                  # architecture, api, deployment, development, user-guide
├── scripts/               # build, development, maintenance, migration
├── build/                 # Generated static frontend (gitignored)
├── storage/               # Runtime data: uploads, downloads, reports, cache (gitignored)
├── assets/                # Committed source assets (wiki icons, illustrations)
├── config/defaults/       # Example env overrides
├── pyproject.toml
├── README.md
└── .github/
```

## Python package (`src/coh_ucs_tools/`)

| Domain | Role |
|--------|------|
| `core/` | Parser, merge, validator, text helpers |
| `analysis/` | Stats, diff, patch chain |
| `io/` | PO/TMX, SGA read/write |
| `locale/` | Locale union builds, coverage, per-language builders |
| `tools/` | Translate, depot, verification |
| `profiles/` | Game profile classification |
| `cli/` | `coh-ucs` entry point |
| `web/` | FastAPI app, API routers, static SPA |
| `config/` | Central path resolution (`config.paths`) |

### Configuration

All default filesystem paths are defined in `coh_ucs_tools.config.paths`:

- `STORAGE_ROOT` → `storage/`
- `UPLOADS_DIR` → `storage/uploads/` (override: `UCS_WEBAPP_UPLOADS`)
- `DOWNLOADS_DIR` → `storage/downloads/`
- `REPORTS_DIR` → `storage/reports/`
- `CACHE_DIR` → `storage/cache/`
- `WEB_DATA_DIR` → `storage/web/data/` (SQLite; override: `SQLITE_PATH`)
- `BUILD_DIST` → `build/dist/`

Legacy root folders (`uploads/`, `downloads/`, `report/`) remain supported for migration via search fallbacks and DB index migration.

## Web layer (`web/`)

```
web/
├── main.py           # FastAPI app, lifespan, static mount
├── api/
│   ├── core.py       # Files, merge, downloads, health
│   └── extended.py   # Analysis, locale, SGA, depot, ops
├── routes.py         # SPA route registry (single source)
├── services.py       # Glossary, audit, MT jobs, batch compare
├── store.py          # UCS file store on disk
├── db.py             # SQLite persistence
├── static/           # SPA source (served in dev; copied to build/dist for CDN)
└── …
```

## Tests

```
tests/
├── unit/             # Core, locale, depot, webhooks
├── api/              # FastAPI TestClient (formerly tests/web/)
├── static/           # Frontend route/i18n/motion checks
├── fixtures/         # Shared UCS test file writers
└── conftest.py
```

## Scripts

| Directory | Scripts |
|-----------|---------|
| `scripts/build/` | `static.py`, `wiki_assets.py`, `download_fonts.py`, `generate_icons.py` |
| `scripts/development/` | `audit_routes.py`, `e2e_playwright.py`, `wiki_screenshots.py` |
| `scripts/maintenance/` | `expand_i18n.py` |
| `scripts/migration/` | One-off migration utilities |

Build static UI for GitHub Pages:

```bash
python scripts/build/static.py --out build/dist
```

## Documentation

| Path | Content |
|------|---------|
| `docs/architecture/` | This file, project report |
| `docs/api/reference.md` | REST + CLI API reference |
| `docs/deployment/guide.md` | Fly.io, Docker, Pages |
| `docs/development/backlog.md` | Engineering backlog |

## Assets

- `assets/wiki-assets/` — Wiki/README icons and animated SVGs (synced to nav icons via `scripts/build/wiki_assets.py`)
- SPA runtime assets remain in `src/coh_ucs_tools/web/static/` (packaged with the wheel)

## Dependency direction

```
cli / web  →  tools, locale, analysis, io  →  core
                    ↓
              config.paths (no business logic)
```

High-level modules must not import from each other’s implementation details across feature boundaries; shared types live in `core` and `config`.
