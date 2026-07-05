"""Static checks for motion layer (motion.js, motion.css, routeScope integration)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTION_JS = ROOT / "webapp" / "static" / "js" / "motion.js"
MOTION_CSS = ROOT / "webapp" / "static" / "css" / "motion.css"
ROUTE_SCOPE = ROOT / "webapp" / "static" / "js" / "routeScope.js"
CORE_JS = ROOT / "webapp" / "static" / "js" / "core.js"
INDEX_HTML = ROOT / "webapp" / "static" / "index.html"
BUILD_STATIC = ROOT / "scripts" / "build_static.py"
SERVICE_WORKER = ROOT / "webapp" / "static" / "service-worker.js"


class MotionStaticTests(unittest.TestCase):
    def test_motion_js_exports(self) -> None:
        text = MOTION_JS.read_text(encoding="utf-8")
        for sym in (
            "prefersReducedMotion",
            "viewTransition",
            "enter",
            "stagger",
            "showToast",
            "animateViewEnter",
            "animatePanelEnter",
            "loadingSkeleton",
        ):
            self.assertIn(f"export function {sym}", text)

    def test_motion_css_reduced_motion(self) -> None:
        css = MOTION_CSS.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("@keyframes motionEnter", css)
        self.assertIn("@keyframes motionToastIn", css)
        self.assertIn(".radar-sweep { animation: none", css)

    def test_route_scope_uses_motion(self) -> None:
        text = ROUTE_SCOPE.read_text(encoding="utf-8")
        self.assertIn('from "./motion.js"', text)
        self.assertIn("animateViewEnter", text)
        self.assertIn("animatePanelEnter", text)
        self.assertIn("setViewAnimate", text)

    def test_core_uses_show_toast(self) -> None:
        text = CORE_JS.read_text(encoding="utf-8")
        self.assertIn("showToast", text)
        self.assertIn("prefersReducedMotion", text)

    def test_index_links_motion_css(self) -> None:
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("motion.css", html)

    def test_service_worker_lists_motion_assets(self) -> None:
        sw = SERVICE_WORKER.read_text(encoding="utf-8")
        self.assertIn("motion.css", sw)
        self.assertIn("motion.js", sw)
        self.assertIn("routeScope.js", sw)

    def test_build_static_cache_and_assets(self) -> None:
        build = BUILD_STATIC.read_text(encoding="utf-8")
        self.assertIn("coh-ucs-v11", build)
        self.assertIn("motion.css", build)
        self.assertIn("motion.js", build)


if __name__ == "__main__":
    unittest.main()
