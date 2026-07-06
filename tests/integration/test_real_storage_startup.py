"""Startup smoke tests using real storage paths (no test temp dirs)."""

from __future__ import annotations

import os
import unittest


class RealStorageStartupTests(unittest.TestCase):
    """Catch regressions that only appear outside isolated test uploads."""

    def setUp(self) -> None:
        self._saved_uploads = os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        self._saved_sqlite = os.environ.pop("SQLITE_PATH", None)

    def tearDown(self) -> None:
        if self._saved_uploads is not None:
            os.environ["UCS_WEBAPP_UPLOADS"] = self._saved_uploads
        else:
            os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        if self._saved_sqlite is not None:
            os.environ["SQLITE_PATH"] = self._saved_sqlite
        else:
            os.environ.pop("SQLITE_PATH", None)

    def test_index_with_default_storage_layout(self) -> None:
        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        with TestClient(app) as client:
            r = client.get("/")
            self.assertEqual(r.status_code, 200, r.text[:500])
            self.assertIn("app.js", r.text)

    def test_legacy_webapp_main_shim_imports(self) -> None:
        from webapp.main import app
        from coh_ucs_tools.web.main import app as canonical

        self.assertIs(app, canonical)
