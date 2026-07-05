"""Tests for hybrid static deploy (build script, CORS, apiUrl)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class CorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.pop("CORS_ORIGINS", None)
        from fastapi.testclient import TestClient
        from webapp.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_cors_preflight_allowed_origin(self) -> None:
        origin = "https://benmed00.github.io"
        res = self.client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-API-Key, Content-Type",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), origin)
        allow_headers = res.headers.get("access-control-allow-headers", "").lower()
        self.assertIn("x-api-key", allow_headers)
        self.assertIn("content-type", allow_headers)

    def test_cors_get_with_origin(self) -> None:
        origin = "https://coh-ucs-tools.pages.dev"
        res = self.client.get("/api/health", headers={"Origin": origin})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), origin)

    def test_cors_github_pages_on_versions(self) -> None:
        origin = "https://benmed00.github.io"
        res = self.client.get("/api/versions", headers={"Origin": origin})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), origin)

    def test_cors_on_auth_error(self) -> None:
        prev = os.environ.get("UCS_API_KEY")
        os.environ["UCS_API_KEY"] = "test-secret"
        try:
            from importlib import reload
            import webapp.main as main_mod

            reload(main_mod)
            from fastapi.testclient import TestClient

            with TestClient(main_mod.app) as client:
                origin = "https://benmed00.github.io"
                res = client.post("/api/files", headers={"Origin": origin})
                self.assertEqual(res.status_code, 401)
                self.assertEqual(res.headers.get("access-control-allow-origin"), origin)
        finally:
            if prev is None:
                os.environ.pop("UCS_API_KEY", None)
            else:
                os.environ["UCS_API_KEY"] = prev
            from importlib import reload
            import webapp.main as main_mod

            reload(main_mod)


class BuildStaticTests(unittest.TestCase):
    def test_build_static_output(self) -> None:
        from scripts.build_static import build_static

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dist"
            build_static(out, "https://coh-ucs-tools.fly.dev", "https://benmed00.github.io/coh-ucs-tools")
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "css" / "app.css").is_file())
            self.assertTrue((out / "js" / "core.js").is_file())
            config = (out / "js" / "config.js").read_text(encoding="utf-8")
            self.assertIn('window.API_BASE = "https://coh-ucs-tools.fly.dev"', config)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('./css/app.css', index)
            self.assertNotIn("/static/css/", index)


class ApiUrlTests(unittest.TestCase):
    def test_api_url_joins_base_and_path(self) -> None:
        core_path = Path(__file__).resolve().parent.parent / "webapp" / "static" / "js" / "core.js"
        text = core_path.read_text(encoding="utf-8")
        self.assertIn("export function apiUrl(path)", text)
        self.assertIn('return (window.API_BASE || "") + path', text)
        self.assertIn("fetch(apiUrl(path)", text)
        self.assertIn("export function isHybridUi()", text)
        self.assertIn('credentials = isHybridUi() ? "omit" : "include"', text)


if __name__ == "__main__":
    unittest.main()
