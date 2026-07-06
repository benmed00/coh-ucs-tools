"""Static checks for motion layer (motion.js, motion.css, routeScope integration)."""

from __future__ import annotations

import unittest

from tests.conftest import REPO_ROOT, STATIC_DIR

MOTION_JS = STATIC_DIR / "js" / "motion.js"
MOTION_CSS = STATIC_DIR / "css" / "motion.css"
ROUTE_SCOPE = STATIC_DIR / "js" / "routeScope.js"
CORE_JS = STATIC_DIR / "js" / "core.js"
INDEX_HTML = STATIC_DIR / "index.html"
BUILD_STATIC = REPO_ROOT / "scripts" / "build" / "static.py"
SERVICE_WORKER = STATIC_DIR / "service-worker.js"


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
        self.assertIn("Promise.allSettled", sw)
        self.assertIn('ASSET_PATHS', sw)

    def test_build_static_cache_and_assets(self) -> None:
        build = BUILD_STATIC.read_text(encoding="utf-8")
        self.assertIn("coh-ucs-v12", build)
        self.assertIn("Promise.allSettled", build)
        self.assertNotIn('"/",', build)
        self.assertIn("motion.css", build)
        self.assertIn("motion.js", build)


if __name__ == "__main__":
    unittest.main()
