# AGENTS.md

## Cursor Cloud specific instructions

This repo is the **CoH UCS Toolkit** — a Python project (no Node/`package.json`). It ships one product with three surfaces that share the same core logic:

- **Web app** (`webapp/`): a FastAPI REST API that also serves a static vanilla-JS single-page frontend. This is the primary runnable service.
- **CLI** (`cli.py`): terminal front-end for compare/statistics/validate/search/merge.
- **Locale builders** (`build_*.py`) and other stdlib scripts.

The startup update script already installs dependencies (`pip install -r requirements.txt coverage ruff pytest`), so you do not need to reinstall. Standard commands live in `README.md`, `CONTRIBUTING.md`, and `.github/workflows/test.yml`; the notes below are only the non-obvious caveats.

### Environment gotchas
- Use **`python3`** — plain `python` is not on `PATH`.
- pip installs console scripts to `~/.local/bin`, which is **not** on `PATH`. Invoke tools as modules: `python3 -m pytest`, `python3 -m ruff`, `python3 -m uvicorn`, `python3 -m coverage`.
- **`PYTHONPATH` must include the repo root** for the webapp, CLI, and tests, because `webapp/` imports top-level modules (`parser`, `game_profiles`, etc.). Prefix commands with `PYTHONPATH=$PWD` (CI does the same).
- **No external services are required.** Storage is embedded SQLite (auto-created at startup, default `webapp/data/app.db`). Redis (`REDIS_URL`) is optional (distributed rate-limiting) and falls back to in-memory. DeepL/Google MT are optional and only used by translation builders.

### Run / test / lint (from repo root)
- Run web app (dev, hot reload): `PYTHONPATH=$PWD python3 -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --reload`
  - UI: `http://127.0.0.1:8000/`, docs: `/docs`, health: `/api/health`.
- Tests (202 pass): `PYTHONPATH=$PWD python3 -m coverage run -m pytest tests/ -q` then `python3 -m coverage report -m`.
- Lint: `python3 -m ruff check . --ignore E501`. Ruff currently reports pre-existing findings and is **non-blocking** in CI (`|| true`); do not treat its exit code as a test failure.
- CLI example: `PYTHONPATH=$PWD python3 cli.py --english <ref.ucs> --russian <target.ucs> statistics` (global `--output`/`--english`/`--russian` come *before* the subcommand).

### UI / GUI testing caveats (important for manual browser testing)
- The SPA wraps route DOM updates in the **View Transitions API** (`webapp/static/js/motion.js`, `routeScope.js`). In the cloud VM's software-WebGL headless Chrome, transitions get skipped and the DOM write for a route lands *after* the follow-up `patchHtml(...)` runs — so **result-rendering routes (Compare, Diff, Analysis) may not render and never fire their `/api/...` request**. The backend endpoints themselves are correct. Verify core logic via the **REST API** (`curl`/`/docs`) or the **CLI**, not by asserting on rendered SPA results.
- **Native file-chooser dialogs cannot be automated** in this browser, so the Upload dropzone's file picker won't open under computer-use. Upload/parse via the REST API instead: `curl -F "file=@/path/file.ucs" "http://127.0.0.1:8000/api/files?game_profile=coh1"`.
- `.ucs` files are **UTF-16-LE with a BOM (FF FE) and CRLF line endings**, `id<TAB>text` per line. Generate fixtures accordingly when testing.
