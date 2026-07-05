#!/usr/bin/env python3
"""Playwright smoke/E2E checks for the CoH UCS webapp."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_view(page, heading: str) -> None:
    """Wait for SPA route to render a section heading in #view."""
    page.wait_for_load_state("domcontentloaded")
    page.locator("#view").get_by_role("heading", name=heading, exact=True).wait_for(
        state="visible", timeout=15000
    )


def _assert_no_route_error(page) -> None:
    banner = page.locator("#view .banner.error")
    assert banner.count() == 0, f"route error visible: {banner.first.inner_text()}"


def _route_heading(page) -> str:
    h = page.locator("#view h2.section-title").first
    h.wait_for(state="visible", timeout=15000)
    return h.inner_text().strip()


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

    port = int(os.environ.get("UCS_E2E_PORT", "0")) or _free_port()
    env["UCS_E2E_PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
    )
    js_errors: list[str] = []
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                import urllib.request

                with urllib.request.urlopen(f"{base}/api/health", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"server did not start on {base}")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda err: js_errors.append(str(err))
                if "Transition was skipped" not in str(err) else None)

            page.goto(f"{base}/")
            page.wait_for_load_state("networkidle")
            assert page.title(), "page should have a title"
            assert page.locator("text=LOCALIZATION").first.is_visible()
            _wait_view(page, "DASHBOARD")
            _assert_no_route_error(page)

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

            # SPA nav — click links without full document reload
            page.locator('nav a[data-route="tools"]').click()
            _wait_view(page, "TOOLS & INTEL")
            _assert_no_route_error(page)

            page.locator('nav a[data-route="settings"]').click()
            _wait_view(page, "SETTINGS")
            _assert_no_route_error(page)
            assert page.locator("#prefs-form").count() == 1
            assert page.locator("#prefs-form input#api-key[type=password]").count() == 1

            # Fast settings churn (regression: async DOM race / innerHTML on null)
            for _ in range(3):
                page.locator('nav a[data-route="dashboard"]').click()
                _wait_view(page, "DASHBOARD")
                page.locator('nav a[data-route="settings"]').click()
                _wait_view(page, "SETTINGS")
            _assert_no_route_error(page)

            # Merge wizard
            page.goto(f"{base}/merge-wizard")
            _wait_view(page, "MERGE WIZARD")
            assert page.get_by_role("link", name="Two-way", exact=True).is_visible()

            # Depots page
            page.goto(f"{base}/depots")
            _wait_view(page, "DEPOTS & SOURCES")

            # Upload page shell
            page.goto(f"{base}/upload")
            _wait_view(page, "UPLOAD & ANALYZE")
            assert page.locator("#game-profile").is_visible()

            # Compare shell
            page.goto(f"{base}/compare")
            _wait_view(page, "COMPARE")

            # About + FAQ (i18n keys, no route crash)
            page.goto(f"{base}/about")
            _wait_view(page, "ABOUT COH UCS TOOLS")
            assert page.locator("#view details summary").first.is_visible()

            # Languages hub
            page.goto(f"{base}/languages")
            _wait_view(page, "LANGUAGES")

            # Footer SPA link
            page.goto(f"{base}/")
            _wait_view(page, "DASHBOARD")
            page.locator('footer a[data-route="about"]').click()
            _wait_view(page, "ABOUT COH UCS TOOLS")

            assert not js_errors, "JS page errors:\n" + "\n".join(js_errors)

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
