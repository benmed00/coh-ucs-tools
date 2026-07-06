#!/usr/bin/env python3
"""Audit SPA and external routes for the web UI."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from coh_ucs_tools.web.main import app  # noqa: E402
from coh_ucs_tools.web.routes import APP_ROUTE_SLUGS
from coh_ucs_tools.web.seo import SPA_SLUGS  # noqa: E402

APP_ROUTES = APP_ROUTE_SLUGS

_tmp = tempfile.TemporaryDirectory()
os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(_tmp.name) / "uploads")
client = TestClient(app)
client.__enter__()  # run lifespan (store + version registry)

try:
    print("=== SPA ROUTE HTTP AUDIT ===")
    for slug in APP_ROUTES:
        path = "/" if slug == "dashboard" else f"/{slug}"
        r = client.get(path)
        ok = r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
        has_app = "app.js" in r.text
        in_seo = slug in SPA_SLUGS or slug == "dashboard"
        flag = "OK" if ok and has_app else "FAIL"
        seo = "yes" if in_seo else "MISSING"
        print(f"{flag:4} {path:22} status={r.status_code} app.js={has_app} seo={seo}")

    missing_seo = [s for s in APP_ROUTES if s not in SPA_SLUGS and s != "dashboard"]
    print("\nIn app.js but not SPA_SLUGS:", missing_seo or "none")

    print("\n=== EXTERNAL / API PATHS ===")
    for path in [
        "/docs", "/redoc", "/openapi.json", "/robots.txt", "/sitemap.xml",
        "/api/health", "/api/versions", "/static/js/app.js", "/static/js/i18n.js",
        "/static/i18n/en.json", "/not-a-real-route",
    ]:
        r = client.get(path)
        print(f"{r.status_code:3} {path}")

    print("\n=== SERVICE WORKER ASSETS ===")
    sw = (ROOT / "src/coh_ucs_tools/web/static/service-worker.js").read_text(encoding="utf-8")
    block = sw.split("ASSET_PATHS = [")[1].split("];")[0]
    for a in re.findall(r'"([^"]+)"', block):
        if a == "/":
            r = client.get("/")
        elif a.startswith("/static/"):
            r = client.get(a)
        else:
            continue
        print(f"{r.status_code:3} {a}")
finally:
    client.__exit__(None, None, None)
    os.environ.pop("UCS_WEBAPP_UPLOADS", None)
    _tmp.cleanup()
