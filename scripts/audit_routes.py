#!/usr/bin/env python3
"""Audit SPA and external routes for the web UI."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from webapp.main import app  # noqa: E402
from webapp.seo import SPA_SLUGS  # noqa: E402

APP_ROUTES = [
    "dashboard", "about", "upload", "compare", "merge", "tools", "diff", "ranges",
    "validator", "languages", "merge-wizard", "install", "mt", "glossary", "timeline",
    "depots", "search", "bookmarks", "patch", "sga", "settings", "editor", "verify",
    "translation", "campaigns", "games",
]

client = TestClient(app)

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
sw = (ROOT / "webapp/static/service-worker.js").read_text(encoding="utf-8")
block = sw.split("ASSETS = [")[1].split("];")[0]
for a in re.findall(r'"([^"]+)"', block):
    if a == "/":
        r = client.get("/")
    elif a.startswith("/static/"):
        r = client.get(a)
    else:
        continue
    print(f"{r.status_code:3} {a}")
