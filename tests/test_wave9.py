"""Wave 9: profile metadata, webhook retry, session expiry, editor SGA inject API."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import BOM_LE
from webapp.auth import create_session_token, peek_session_token, verify_session_token


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class ProfileMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")
        os.environ["UCS_SESSION_SECRET"] = "test-secret-wave9"

        from fastapi.testclient import TestClient
        from webapp.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        os.environ.pop("UCS_SESSION_SECRET", None)
        cls._tmp.cleanup()

    def test_upload_persists_detected_profile(self) -> None:
        res = self.client.post(
            "/api/files",
            files={"file": ("coh1.ucs", ucs_bytes({559200: "x", 1: "a"}), "application/octet-stream")},
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()["file"]
        self.assertEqual(body["detected_profile"], "coh1")
        self.assertGreater(body["profile_confidence"], 0.5)

    def test_list_files_includes_profile(self) -> None:
        fid = self.client.post(
            "/api/files",
            files={"file": ("t.ucs", ucs_bytes({1000: "a"}), "application/octet-stream")},
        ).json()["file"]["id"]
        listed = self.client.get("/api/files").json()["files"]
        match = next(f for f in listed if f["id"] == fid)
        self.assertIn("detected_profile", match)


class WebhookRetryTests(unittest.TestCase):
    def test_fire_webhooks_retries_then_dead_letters(self) -> None:
        from webapp import db as db_mod
        from webapp.db import get_db
        from webapp.services import fire_webhooks

        if db_mod._db is not None:
            db_mod._db._apply_schema_migrations()
        get_db().execute("DELETE FROM webhooks")
        get_db().execute("DELETE FROM webhook_deliveries")
        get_db().execute(
            "INSERT INTO webhooks(id, url, events, created_at) VALUES (?,?,?,?)",
            ("w9", "http://127.0.0.1:9/fail", json.dumps(["merge_complete"]), 0),
        )
        with patch("webapp.services._post_webhook", return_value=(False, None, "down")):
            with patch("webapp.services.time.sleep"):
                fire_webhooks("merge_complete", {"job_id": "x"})
        row = get_db().fetchone(
            "SELECT attempt, dead_letter, success FROM webhook_deliveries ORDER BY id DESC LIMIT 1"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["attempt"], 3)
        self.assertEqual(row["dead_letter"], 1)
        self.assertEqual(row["success"], 0)

    def test_retry_dead_letters_endpoint(self) -> None:
        from webapp import db as db_mod
        from webapp.db import get_db
        from webapp.services import _log_webhook_delivery, retry_dead_letter_webhooks

        if db_mod._db is not None:
            db_mod._db._apply_schema_migrations()
        get_db().execute("DELETE FROM webhook_deliveries")
        _log_webhook_delivery(
            event="merge_complete", url="http://127.0.0.1:9/x",
            success=False, status_code=None, error="fail", payload={"a": 1},
            attempt=3, dead_letter=True,
        )
        with patch("webapp.services._post_webhook", return_value=(True, 200, "")):
            summary = retry_dead_letter_webhooks(limit=5)
        self.assertEqual(summary["retried"], 1)
        self.assertEqual(summary["succeeded"], 1)


class SessionExpiryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["UCS_SESSION_SECRET"] = "wave9-expiry-secret"
        os.environ["UCS_ADMIN_PASSWORD"] = "pass"

        from fastapi.testclient import TestClient
        from webapp.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_SESSION_SECRET", None)
        os.environ.pop("UCS_ADMIN_PASSWORD", None)

    def test_auth_status_includes_session_expiry(self) -> None:
        token = create_session_token("admin", ttl_s=7200)
        res = self.client.get("/api/auth/status", cookies={"ucs_session": token})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["authenticated"])
        self.assertIn("session_expires_in_s", body)
        self.assertGreater(body["session_expires_in_s"], 0)
        self.assertFalse(body["session_expired"])

    def test_expired_token_peek_vs_verify(self) -> None:
        token = create_session_token("admin", ttl_s=-10)
        payload = peek_session_token(token)
        self.assertIsNotNone(payload)
        self.assertIsNone(verify_session_token(token))


if __name__ == "__main__":
    unittest.main()
