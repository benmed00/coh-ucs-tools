"""Wave 8: webhook delivery log, profile strict on compare/merge, SGA inject API."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from coh_ucs_tools.core.parser import BOM_LE


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class WebhookDeliveryLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")

        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        cls._tmp.cleanup()

    def setUp(self) -> None:
        from coh_ucs_tools.web import db as db_mod
        from coh_ucs_tools.web.db import get_db
        if db_mod._db is not None:
            db_mod._db._apply_schema_migrations()
        get_db().execute("DELETE FROM webhooks")
        get_db().execute("DELETE FROM webhook_deliveries")

    def test_delivery_logged_on_failure(self) -> None:
        from coh_ucs_tools.web.db import get_db
        get_db().execute(
            "INSERT INTO webhooks(id, url, events, created_at) VALUES (?,?,?,?)",
            ("wh8", "http://127.0.0.1:9/hook", json.dumps(["merge_complete"]), 0),
        )
        a = self.client.post(
            "/api/files",
            files={"file": ("a.ucs", ucs_bytes({1: "a"}), "application/octet-stream")},
        ).json()["file"]["id"]
        b = self.client.post(
            "/api/files",
            files={"file": ("b.ucs", ucs_bytes({1: "a", 2: "b"}), "application/octet-stream")},
        ).json()["file"]["id"]
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            self.client.post("/api/merge", json={
                "target_id": a, "source_id": b, "mode": "placeholder",
            })
        res = self.client.get("/api/webhooks/deliveries")
        self.assertEqual(res.status_code, 200)
        deliveries = res.json()["deliveries"]
        self.assertEqual(len(deliveries), 1)
        self.assertFalse(deliveries[0]["success"])
        self.assertIn("connection refused", deliveries[0]["error"])

    def test_delivery_logged_on_success(self) -> None:
        from coh_ucs_tools.web.db import get_db
        get_db().execute(
            "INSERT INTO webhooks(id, url, events, created_at) VALUES (?,?,?,?)",
            ("wh8b", "http://127.0.0.1:9/ok", json.dumps(["compare_complete"]), 0),
        )
        a = self.client.post(
            "/api/files",
            files={"file": ("ba.ucs", ucs_bytes({1: "a"}), "application/octet-stream")},
        ).json()["file"]["id"]
        b = self.client.post(
            "/api/files",
            files={"file": ("bb.ucs", ucs_bytes({2: "b"}), "application/octet-stream")},
        ).json()["file"]["id"]
        mock_resp = type("R", (), {"status": 200, "getcode": lambda self: 200, "__enter__": lambda s: s, "__exit__": lambda *a: None})()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            self.client.post("/api/batch/compare", json={"file_ids": [a, b]})
        res = self.client.get("/api/webhooks/deliveries?limit=5")
        self.assertTrue(any(d["event"] == "compare_complete" and d["success"] for d in res.json()["deliveries"]))


class ProfileStrictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")

        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        cls._tmp.cleanup()

    def test_compare_strict_rejects_mismatch(self) -> None:
        coh1 = self.client.post(
            "/api/files",
            files={"file": ("coh1.ucs", ucs_bytes({559200: "Normandy", 1: "x"}), "application/octet-stream")},
        ).json()["file"]["id"]
        coh2 = self.client.post(
            "/api/files",
            files={"file": ("coh2.ucs", ucs_bytes({i * 1000: f"k{i}" for i in range(1, 6)}), "application/octet-stream")},
        ).json()["file"]["id"]
        ok = self.client.get(f"/api/compare?a={coh1}&b={coh2}&game_profile=coh1&strict_profile=false")
        self.assertEqual(ok.status_code, 200)
        bad = self.client.get(f"/api/compare?a={coh1}&b={coh2}&game_profile=coh2&strict_profile=true")
        self.assertEqual(bad.status_code, 422)
        self.assertIn("mismatches", bad.json()["detail"])

    def test_merge_strict_allows_matching_files(self) -> None:
        a = self.client.post(
            "/api/files",
            files={"file": ("m1.ucs", ucs_bytes({559200: "x", 1: "a"}), "application/octet-stream")},
        ).json()["file"]["id"]
        b = self.client.post(
            "/api/files",
            files={"file": ("m2.ucs", ucs_bytes({559200: "x", 2: "b"}), "application/octet-stream")},
        ).json()["file"]["id"]
        res = self.client.post(
            "/api/merge?game_profile=coh1&strict_profile=true",
            json={"target_id": a, "source_id": b, "mode": "placeholder"},
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
