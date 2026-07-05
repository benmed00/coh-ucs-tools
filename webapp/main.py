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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.responses import Response as StarletteResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .deps import KNOWN_VERSIONS, LOCALE_VERSIONS
from . import services
from .seo import (
    GOOGLE_VERIFICATION_HTML,
    inject_index_html,
    indexnow_key as get_indexnow_key,
    is_spa_path,
    robots_txt,
    sitemap_xml,
    ui_site_url,
)
from .store import FileStore

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_CORS_ORIGINS = [
    "https://coh-ucs-tools.fly.dev",
    "https://coh-ucs-tools.pages.dev",
    "https://benmed00.github.io",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]


def cors_origins() -> list[str]:
    """Return allowed CORS origins; ``CORS_ORIGINS`` adds comma-separated extras."""
    extra = os.environ.get("CORS_ORIGINS", "")
    origins = list(DEFAULT_CORS_ORIGINS)
    if extra:
        for item in extra.split(","):
            origin = item.strip()
            if origin and origin not in origins:
                origins.append(origin)
    return origins


def with_cors(request: Request, response: StarletteResponse) -> StarletteResponse:
    """Attach CORS headers when middleware returns before CORSMiddleware runs."""
    origin = request.headers.get("origin")
    if origin and origin in cors_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        vary = response.headers.get("Vary")
        response.headers["Vary"] = "Origin" if not vary else f"{vary}, Origin"
    return response


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
    ``SQLITE_PATH`` overrides the SQLite database path.
    """
    from .db import get_db
    services.ensure_storage()
    get_db()  # init + migrate JSON storage
    store = FileStore(os.environ.get("UCS_WEBAPP_UPLOADS", "uploads"))
    app.state.store = store
    for meta in KNOWN_VERSIONS:
        store.register_version(
            meta["id"], meta["name"], meta["path"],
            origin=meta["origin"], completeness=meta["completeness"],
            notes=meta["notes"],
        )
    for meta in LOCALE_VERSIONS:
        if meta["path"].exists():
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
)

@app.middleware("http")
async def optional_api_key_and_rate_limit(request: Request, call_next):
    """API key, session cookie, Bearer token, or OAuth session; plus rate limits."""
    from .auth import authenticate_request, is_public_path, require_auth_on_mutations
    from .rate_limit import check_rate_limit

    path = request.url.path

    if path.startswith("/api/") and require_auth_on_mutations() and not is_public_path(path, request.method):
        user = authenticate_request(request)
        if user is None:
            return with_cors(
                request,
                JSONResponse(status_code=401, content={"detail": "Authentication required"}),
            )

    if path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        is_upload = request.method == "POST" and request.url.path.rstrip("/") == "/api/files"
        allowed, reason = check_rate_limit(ip, upload=is_upload)
        if not allowed:
            return with_cors(
                request,
                JSONResponse(status_code=429, content={"detail": reason}),
            )

    response = await call_next(request)
    return response


@app.middleware("http")
async def seo_response_headers(request: Request, call_next):
    """Cache SEO assets and block API indexing."""
    response = await call_next(request)
    path = request.url.path

    if path.startswith("/api/"):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    elif path.startswith("/static/"):
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    elif path in ("/robots.txt", "/sitemap.xml"):
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "public, max-age=3600"

    return response


def _render_index_html() -> str:
    raw = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return inject_index_html(raw, base_url=ui_site_url(), base_path="")


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse(_render_index_html())


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request) -> PlainTextResponse:
    origin = str(request.base_url).rstrip("/")
    return PlainTextResponse(
        robots_txt(sitemap_url=f"{origin}/sitemap.xml"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap() -> Response:
    return Response(
        content=sitemap_xml(include_api_docs=True),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "icons" / "icon-192.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get(f"/{GOOGLE_VERIFICATION_HTML}", include_in_schema=False)
def google_site_verification() -> PlainTextResponse:
    path = STATIC_DIR / "seo" / GOOGLE_VERIFICATION_HTML
    return PlainTextResponse(
        path.read_text(encoding="utf-8").strip() + "\n",
        media_type="text/html",
    )


@app.get("/{key}.txt", include_in_schema=False)
def indexnow_verification(key: str) -> PlainTextResponse:
    expected = get_indexnow_key()
    if not expected or key != expected:
        raise HTTPException(status_code=404)
    return PlainTextResponse(expected + "\n", media_type="text/plain")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/{spa_path:path}", include_in_schema=False)
def spa_fallback(spa_path: str) -> HTMLResponse:
    """Serve SPA shell for path-based client routes (e.g. ``/upload``)."""
    if is_spa_path(spa_path):
        return HTMLResponse(_render_index_html())
    raise HTTPException(status_code=404)
