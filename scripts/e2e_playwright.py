#!/usr/bin/env python3
"""Playwright smoke/E2E checks for the CoH UCS webapp."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["UCS_WEBAPP_UPLOADS"] = str(ROOT / ".e2e-uploads")
    env["UCS_SESSION_SECRET"] = "e2e-test-secret"
    env["UCS_ADMIN_USER"] = "admin"
    env["UCS_ADMIN_PASSWORD"] = "e2e-pass"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.main:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=str(ROOT),
        env=env,
    )
    try:
        time.sleep(3)
        base = "http://127.0.0.1:8765"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            page.goto(f"{base}/")
            page.wait_for_timeout(1500)
            assert page.title(), "page should have a title"
            assert page.locator("text=LOCALIZATION").first.is_visible()

            status = page.request.get(f"{base}/api/auth/status")
            assert status.ok
            body = status.json()
            assert body.get("auth_enabled") is True

            login = page.request.post(
                f"{base}/api/auth/login",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"username": "admin", "password": "e2e-pass"}),
            )
            assert login.ok, login.text()
            token = login.json().get("token")
            assert token

            bm = page.request.post(
                f"{base}/api/bookmarks",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps({"ids": [12345]}),
            )
            assert bm.ok, bm.text()

            cov = page.request.get(f"{base}/api/languages/coverage")
            assert cov.ok
            assert "locales" in cov.json()

            chain = page.request.get(f"{base}/api/versions/patch-chain")
            assert chain.ok
            assert "chain" in chain.json()

            # UI routes — merge wizard
            page.goto(f"{base}/merge-wizard")
            page.wait_for_timeout(1200)
            assert page.locator("text=MERGE WIZARD").is_visible()
            assert page.locator("text=Two-way").is_visible()

            # Depots page
            page.goto(f"{base}/depots")
            page.wait_for_timeout(1200)
            assert page.locator("text=DEPOTS").is_visible()

            # Upload page shell
            page.goto(f"{base}/upload")
            page.wait_for_timeout(1200)
            assert page.locator("text=UPLOAD").is_visible()
            assert page.locator("#game-profile").is_visible()

            # Settings
            page.goto(f"{base}/settings")
            page.wait_for_timeout(1200)
            assert page.locator("text=SETTINGS").is_visible()

            page.screenshot(path=str(ROOT / "e2e-dashboard.png"), full_page=True)
            browser.close()
        print("E2E checks passed")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
