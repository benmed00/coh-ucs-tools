"""Static checks for route lifecycle helpers (routeScope.js)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTE_SCOPE = ROOT / "webapp" / "static" / "js" / "routeScope.js"
APP_JS = ROOT / "webapp" / "static" / "js" / "app.js"
CORE_JS = ROOT / "webapp" / "static" / "js" / "core.js"


class RouteScopeStaticTests(unittest.TestCase):
    def test_route_scope_module_exports(self) -> None:
        text = ROUTE_SCOPE.read_text(encoding="utf-8")
        for sym in (
            "beginRoute",
            "routeAlive",
            "routeSignal",
            "setViewHtml",
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
        build = (ROOT / "scripts" / "build_static.py").read_text(encoding="utf-8")
        self.assertIn("routeScope.js", build)


if __name__ == "__main__":
    unittest.main()
