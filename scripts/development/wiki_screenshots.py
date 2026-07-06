#!/usr/bin/env python3
"""Capture SPA screenshots for the GitHub wiki."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# heading = #view h2.section-title text; content = selector that appears after async load
PAGES: list[tuple[str, str, str, str]] = [
    ("dashboard", "/", "DASHBOARD", "#view .grid.cols-2 .card, #view .data, #view .empty"),
    ("upload", "/upload", "UPLOAD & ANALYZE", "#game-profile, #upload-form, #view form"),
    ("compare", "/compare", "COMPARE", "#view form, #view select, #view .btn"),
    ("diff", "/diff", "DIFF", "#view form, #view select"),
    ("merge-wizard", "/merge-wizard", "MERGE WIZARD", "#view .tab-bar, #view form, #view a"),
    ("validator", "/validator", "VALIDATOR", "#view form, #view select"),
    ("verify", "/verify", "VERIFY CHECKLIST", "#view form, #view select"),
    ("languages", "/languages", "LANGUAGES", "#view .card, #view .grid, #view .empty"),
    ("search", "/search", "SEARCH", "#view form, #view input"),
    ("settings", "/settings", "SETTINGS", "#prefs-form"),
    ("depots", "/depots", "DEPOTS & SOURCES", "#view .card, #view .grid"),
    ("tools", "/tools", "TOOLS & INTEL", "#view .tool-card, #view .grid"),
    ("about", "/about", "ABOUT COH UCS TOOLS", "#view details, #view .faq"),
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_route(page, heading: str, content_selector: str, *, timeout_ms: int = 45000) -> None:
    """Wait until the SPA route has finished async render."""
    page.locator("#view").get_by_role("heading", name=heading, exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    page.locator(content_selector).first.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(600)


def _capture(page, out: Path, name: str, path: str, heading: str, content_selector: str) -> None:
    page.goto(path, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    _wait_for_route(page, heading, content_selector)
    page.screenshot(path=str(out / f"{name}.png"), full_page=True)
    print(f"captured {name}.png")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description="Capture wiki screenshots for CoH UCS Tools SPA")
    ap.add_argument("out_dir", nargs="?", default=str(ROOT / "wiki-screenshots"))
    ap.add_argument(
        "--live",
        action="store_true",
        help="Capture from GitHub Pages (hybrid UI + Fly API) instead of local uvicorn",
    )
    ap.add_argument(
        "--base",
        default="https://benmed00.github.io/coh-ucs-tools",
        help="Base URL when --live (default: GitHub Pages)",
    )
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    proc = None
    env = os.environ.copy()
    env["UCS_WEBAPP_UPLOADS"] = str(ROOT / "storage" / "e2e" / "uploads")

    if args.live:
        base = args.base.rstrip("/")
    else:
        port = _free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "coh_ucs_tools.web.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(ROOT),
            env=env,
        )
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
            proc.terminate()
            raise RuntimeError(f"server did not start on {base}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            for name, route, heading, content in PAGES:
                url = f"{base}{route}" if route != "/" else f"{base}/"
                _capture(page, out, name, url, heading, content)
            browser.close()
        print(f"screenshots saved to {out}")
        return 0
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
