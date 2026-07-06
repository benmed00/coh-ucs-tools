"""Tests for SPA router static exports and route name parity."""

from __future__ import annotations

import re
import unittest


from tests.conftest import STATIC_DIR

ROUTER_JS = STATIC_DIR / "js" / "router.js"
APP_JS = STATIC_DIR / "js" / "app.js"


class RouterStaticTests(unittest.TestCase):
    def test_router_exports_parse_route_from_href(self) -> None:
        text = ROUTER_JS.read_text(encoding="utf-8")
        self.assertIn("export function parseRouteFromHref", text)
        self.assertIn("export const ROUTE_NAMES", text)
        self.assertIn("parseRouteFromHref(a.href)", text)

    def test_route_names_match_app_routes(self) -> None:
        router = ROUTER_JS.read_text(encoding="utf-8")
        app = APP_JS.read_text(encoding="utf-8")
        m = re.search(r"export const ROUTE_NAMES = new Set\(\[(.*?)\]\)", router, re.S)
        self.assertIsNotNone(m)
        router_names = set(re.findall(r'"([^"]+)"', m.group(1)))
        m2 = re.search(r"const routes = \{(.*?)\};", app, re.S)
        self.assertIsNotNone(m2)
        app_names = set(re.findall(r'"([^"]+)":\s*render|\n\s+(\w+):\s*render', m2.group(1)))
        flat = {n for pair in app_names for n in pair if n}
        self.assertEqual(router_names, flat)


if __name__ == "__main__":
    unittest.main()
