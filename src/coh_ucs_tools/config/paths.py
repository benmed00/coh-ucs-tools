"""Filesystem layout: project root, runtime storage, and build output paths."""

from __future__ import annotations

import os
from pathlib import Path


def _find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()
STORAGE_ROOT = Path(os.environ.get("COH_STORAGE_ROOT", PROJECT_ROOT / "storage"))
BUILD_ROOT = Path(os.environ.get("COH_BUILD_ROOT", PROJECT_ROOT / "build"))

# Runtime storage (gitignored)
UPLOADS_DIR = Path(os.environ.get("UCS_WEBAPP_UPLOADS", STORAGE_ROOT / "uploads"))
DOWNLOADS_DIR = STORAGE_ROOT / "downloads"
REPORTS_DIR = STORAGE_ROOT / "reports"
GENERATED_DIR = STORAGE_ROOT / "generated"
CACHE_DIR = STORAGE_ROOT / "cache"
JOBS_DIR = STORAGE_ROOT / "jobs"
VERSIONS_DIR = STORAGE_ROOT / "versions"

# Web persistence (SQLite + legacy JSON)
WEB_DATA_DIR = STORAGE_ROOT / "web" / "data"
WEB_STORAGE_DIR = STORAGE_ROOT / "web" / "storage"

# Build outputs
BUILD_DIST = BUILD_ROOT / "dist"
BUILD_VERIFY = BUILD_ROOT / "verify"
BUILD_CHECK = BUILD_ROOT / "check"
BUILD_PREVIEW = BUILD_ROOT / "preview"
BUILD_TEST = BUILD_ROOT / "test-builds"

# Assets (source, committed)
ASSETS_ROOT = PROJECT_ROOT / "assets"


def default_uploads_dir() -> Path:
    """Return the active web upload directory (env override or storage default)."""
    return Path(os.environ.get("UCS_WEBAPP_UPLOADS", str(STORAGE_ROOT / "uploads")))


def resolve_path(path: Path | str, *, base: Path | None = None) -> Path:
    """Resolve a path relative to project root when not absolute."""
    p = Path(path)
    if p.is_absolute():
        return p
    return (base or PROJECT_ROOT) / p


def ensure_storage_layout() -> None:
    """Create runtime storage directories (no-op if they already exist)."""
    for d in (
        UPLOADS_DIR,
        DOWNLOADS_DIR,
        REPORTS_DIR,
        GENERATED_DIR,
        CACHE_DIR,
        JOBS_DIR,
        VERSIONS_DIR,
        WEB_DATA_DIR,
        WEB_STORAGE_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
