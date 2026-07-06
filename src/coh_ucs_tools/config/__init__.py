"""Central configuration and path resolution for CoH UCS Tools."""

from coh_ucs_tools.config.paths import (
    BUILD_ROOT,
    CACHE_DIR,
    DOWNLOADS_DIR,
    GENERATED_DIR,
    JOBS_DIR,
    PROJECT_ROOT,
    REPORTS_DIR,
    STORAGE_ROOT,
    UPLOADS_DIR,
    WEB_DATA_DIR,
    WEB_STORAGE_DIR,
    default_uploads_dir,
    ensure_storage_layout,
    resolve_path,
)

__all__ = [
    "BUILD_ROOT",
    "CACHE_DIR",
    "DOWNLOADS_DIR",
    "GENERATED_DIR",
    "JOBS_DIR",
    "PROJECT_ROOT",
    "REPORTS_DIR",
    "STORAGE_ROOT",
    "UPLOADS_DIR",
    "WEB_DATA_DIR",
    "WEB_STORAGE_DIR",
    "default_uploads_dir",
    "ensure_storage_layout",
    "resolve_path",
]
