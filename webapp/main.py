"""FastAPI application entry point.

Run with::

    python -m uvicorn webapp.main:app --reload

Serves the REST API under ``/api`` (OpenAPI docs at ``/docs`` and
``/redoc``) and the static single-page frontend from ``webapp/static/``.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .deps import KNOWN_VERSIONS
from . import services
from .store import FileStore

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

DESCRIPTION = """
**Company of Heroes 1 `.ucs` localization toolkit — as a web service.**

UCS files are Relic's localization tables: UTF-16-LE, `FF FE` BOM, CRLF line
endings, one `numeric_id<TAB>text` entry per line. When the engine cannot
find an id it renders `$id No Key` in-game — which is exactly what this
service helps you hunt down.

What you can do here:

* **Upload & analyze** any `.ucs` file — encoding/BOM detection, duplicate
  and invalid-line reporting, full validation, searchable entry browser.
* **Compare** two files — coverage percentages and missing-id ranges both ways.
* **Merge** — graft the missing ids of one file onto another, either as
  `<MISSING>` placeholders or by copying the source text verbatim.
  *No translation is ever invented, and originals are never modified.*
* **Download** the built-in registry of known CoH1 localization versions.

Built on the battle-tested CLI toolkit; parsing, validation, statistics and
merge logic are the exact same code paths.
"""

TAGS_METADATA = [
    {"name": "files", "description": "Upload, list, inspect, browse and delete UCS files."},
    {"name": "analysis", "description": "Validation, diff, lint, search and comparison statistics."},
    {"name": "merge", "description": "Merge two files and download the result. Never touches originals."},
    {"name": "versions", "description": "Built-in registry of known CoH1 UCS localization versions."},
    {"name": "tools", "description": "Curated external tools and community references."},
    {"name": "meta", "description": "Service health and audit log."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the file store and register known versions found on disk.

    ``UCS_WEBAPP_UPLOADS`` overrides the storage directory (used by tests).
    """
    services.ensure_storage()
    store = FileStore(os.environ.get("UCS_WEBAPP_UPLOADS", "uploads"))
    app.state.store = store
    for meta in KNOWN_VERSIONS:
        store.register_version(
            meta["id"], meta["name"], meta["path"],
            origin=meta["origin"], completeness=meta["completeness"],
            notes=meta["notes"],
        )
    removed = services.cleanup_old_uploads(store, max_age_hours=24)
    if removed:
        logger.info("Startup cleanup removed %d stale upload(s)", removed)
    logger.info("Startup complete: %d file(s), %d version(s) registered",
                len(store.list()), len(store.list("version")))
    yield


app = FastAPI(
    title="CoH UCS Tools",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    contact={"name": "CoH UCS Toolkit"},
    license_info={"name": "MIT"},
)

app.include_router(router)


@app.middleware("http")
async def optional_api_key_and_rate_limit(request: Request, call_next):
    """Optional API key check (``UCS_API_KEY`` env) and basic rate limiting."""
    api_key = os.environ.get("UCS_API_KEY")
    if api_key and request.url.path.startswith("/api/"):
        header = request.headers.get("X-API-Key", "")
        if header != api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    response = await call_next(request)
    return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
