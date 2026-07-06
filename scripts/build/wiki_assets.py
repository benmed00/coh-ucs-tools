#!/usr/bin/env python3
"""Sync wiki SVG/GIF assets and optionally build GIF loops from the local SPA."""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS = ROOT / "assets" / "wiki-assets"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def sync_assets(out_dir: Path) -> None:
    """Copy icons/ and animated/ into wiki images tree."""
    for sub in ("icons", "animated"):
        src = ASSETS / sub
        dst = out_dir / sub
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    print(f"synced wiki assets -> {out_dir}")


def sync_nav_icons() -> None:
    """Copy canonical wiki icons into the webapp nav icon directory."""
    src = ASSETS / "icons"
    dst = ROOT / "src" / "coh_ucs_tools" / "web" / "static" / "icons" / "nav"
    dst.mkdir(parents=True, exist_ok=True)
    for svg in src.glob("*.svg"):
        shutil.copy2(svg, dst / svg.name)
    print(f"synced nav icons -> {dst}")


def build_gifs(out_dir: Path) -> None:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — skip GIF generation (pip install Pillow)", file=sys.stderr)
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — skip GIF", file=sys.stderr)
        return

    gif_dir = out_dir / "animated"
    gif_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "coh_ucs_tools.web.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
    )
    frames_dir = out_dir / "_gif_frames"
    frames_dir.mkdir(exist_ok=True)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                import urllib.request

                with urllib.request.urlopen(f"{base}/api/health", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.4)
        else:
            raise RuntimeError("server did not start")

        specs = [
            ("upload-dropzone.gif", f"{base}/upload", "#dropzone", 8, 180),
            ("dashboard-radar.gif", f"{base}/", "#hero-canvas", 10, 150),
        ]
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            for name, url, selector, count, delay_ms in specs:
                page.goto(url, wait_until="networkidle")
                page.locator("#view h2.section-title").first.wait_for(state="visible", timeout=20000)
                loc = page.locator(selector)
                if loc.count() == 0:
                    loc = page.locator("#view")
                box = loc.first.bounding_box()
                if not box:
                    continue
                pad = 12
                clip = {
                    "x": max(0, box["x"] - pad),
                    "y": max(0, box["y"] - pad),
                    "width": min(1440, box["width"] + pad * 2),
                    "height": min(900, box["height"] + pad * 2),
                }
                shots: list[Path] = []
                for i in range(count):
                    shot = frames_dir / f"{name}_{i}.png"
                    page.screenshot(path=str(shot), clip=clip)
                    shots.append(shot)
                    page.wait_for_timeout(delay_ms)
                imgs = [Image.open(s).convert("P", palette=Image.ADAPTIVE, colors=48) for s in shots]
                out = gif_dir / name
                imgs[0].save(
                    out,
                    save_all=True,
                    append_images=imgs[1:],
                    duration=delay_ms,
                    loop=0,
                    optimize=True,
                )
                print(f"built {out.name} ({len(imgs)} frames)")
            browser.close()
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description="Build and sync CoH UCS wiki visual assets")
    ap.add_argument("out_dir", nargs="?", default=str(Path.home() / "coh-wiki-images"))
    ap.add_argument("--gif", action="store_true", help="Build GIF loops (requires Pillow + Playwright)")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sync_assets(out)
    sync_nav_icons()
    if args.gif:
        build_gifs(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
