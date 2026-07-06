"""Static checks for route lifecycle helpers (routeScope.js)."""

from __future__ import annotations

import unittest

from tests.conftest import REPO_ROOT, STATIC_DIR

ROUTE_SCOPE = STATIC_DIR / "js" / "routeScope.js"
APP_JS = STATIC_DIR / "js" / "app.js"
CORE_JS = STATIC_DIR / "js" / "core.js"


class RouteScopeStaticTests(unittest.TestCase):
    def test_route_scope_module_exports(self) -> None:
        text = ROUTE_SCOPE.read_text(encoding="utf-8")
        for sym in (
            "beginRoute",
            "routeAlive",
            "routeSignal",
            "setViewHtml",
            "setViewAnimate",
            "patchHtml",
            "q",
            "RouteAbortError",
            "isRouteAbortError",
        ):
            self.assertIn(f"export function {sym}" if sym != "RouteAbortError" else f"export class {sym}", text)

    def test_app_wires_begin_route(self) -> None:
        app = APP_JS.read_text(encoding="utf-8")
        self.assertIn("beginRoute()", app)
        self.assertIn("isRouteAbortError", app)

    def test_core_api_uses_route_signal(self) -> None:
        core = CORE_JS.read_text(encoding="utf-8")
        self.assertIn("routeSignal()", core)

    def test_build_includes_route_scope(self) -> None:
        build = (REPO_ROOT / "scripts" / "build" / "static.py").read_text(encoding="utf-8")
        self.assertIn("routeScope.js", build)


if __name__ == "__main__":
    unittest.main()
