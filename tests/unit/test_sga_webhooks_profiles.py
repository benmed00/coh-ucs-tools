"""Wave 7: per-file SGA compression, webhooks, game profile fixtures, UI E2E."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from tests.fixtures.ucs import write_coh1_fixture, write_coh2_fixture, write_dow1_fixture
from coh_ucs_tools.profiles.game import classify_document
from coh_ucs_tools.core.parser import BOM_LE
from coh_ucs_tools.io.sga import pack_sga, read_sga, repack_sga


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class SgaPerFileCompressionTests(unittest.TestCase):
    def test_mixed_compression_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mixed.sga"
            pack_sga(out, {
                "A/a.bin": b"aaaa" * 200,
                "B/b.bin": b"bbbb" * 50,
            }, compress_paths={"A/a.bin": True, "B/b.bin": False})
            arch = read_sga(out)
            by_path = {e.full_path: e for e in arch.files}
            self.assertTrue(by_path["A/a.bin"].compressed)
            self.assertFalse(by_path["B/b.bin"].compressed)

    def test_repack_preserves_per_entry_compression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.sga"
            pack_sga(src, {
                "Locale/English/x.ucs": b"x" * 300,
                "Data/y.txt": b"plain",
            }, compress_paths={"Locale/English/x.ucs": True, "Data/y.txt": False})
            dst = Path(tmp) / "dst.sga"
            repack_sga(src, {"Data/y.txt": b"plain-updated"}, dst)
            arch = read_sga(dst)
            by_path = {e.full_path: e for e in arch.files}
            self.assertTrue(by_path["Locale/English/x.ucs"].compressed)
            self.assertFalse(by_path["Data/y.txt"].compressed)


class GameProfileFixtureTests(unittest.TestCase):
    def test_coh1_fixture_classifies_coh1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_coh1_fixture(Path(tmp) / "coh1.ucs")
            from coh_ucs_tools.core.parser import parse_file
            doc = parse_file(path)
            result = classify_document(doc)
            self.assertEqual(result["best_match"], "coh1")
            self.assertGreater(result["confidence"], 0.5)

    def test_coh2_fixture_classifies_coh2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_coh2_fixture(Path(tmp) / "coh2.ucs")
            from coh_ucs_tools.core.parser import parse_file
            doc = parse_file(path)
            result = classify_document(doc)
            self.assertEqual(result["best_match"], "coh2")

    def test_dow1_fixture_detects_bomless(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_dow1_fixture(Path(tmp) / "dow1.ucs")
            from coh_ucs_tools.core.parser import parse_file
            doc = parse_file(path)
            self.assertFalse(doc.has_bom)
            result = classify_document(doc)
            self.assertIn(result["best_match"], ("dow1", "coh1", "coh2"))


class WebhookTests(unittest.TestCase):
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
        from coh_ucs_tools.web.db import get_db
        get_db().execute("DELETE FROM webhooks")

    def test_merge_fires_webhook(self) -> None:
        from coh_ucs_tools.web.db import get_db
        get_db().execute(
            "INSERT OR REPLACE INTO webhooks(id, url, events, created_at) VALUES (?,?,?,?)",
            ("wh1", "http://127.0.0.1:9/hook", json.dumps(["merge_complete"]), 0),
        )
        a = self.client.post(
            "/api/files",
            files={"file": ("a.ucs", ucs_bytes({1: "a"}), "application/octet-stream")},
        ).json()["file"]["id"]
        b = self.client.post(
            "/api/files",
            files={"file": ("b.ucs", ucs_bytes({1: "a", 2: "b"}), "application/octet-stream")},
        ).json()["file"]["id"]
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = lambda *a: None
            res = self.client.post("/api/merge", json={
                "target_id": a, "source_id": b, "mode": "placeholder",
            })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mock_open.called)

    def test_list_webhooks(self) -> None:
        self.client.post("/api/webhooks", json={
            "url": "https://example.com/hook", "events": ["merge_complete"],
        })
        res = self.client.get("/api/webhooks")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.json()["webhooks"]), 1)

    def test_batch_compare_fires_webhook(self) -> None:
        from coh_ucs_tools.web.db import get_db
        get_db().execute(
            "INSERT OR REPLACE INTO webhooks(id, url, events, created_at) VALUES (?,?,?,?)",
            ("wh2", "http://127.0.0.1:9/compare", json.dumps(["compare_complete"]), 0),
        )
        a = self.client.post(
            "/api/files",
            files={"file": ("ba.ucs", ucs_bytes({1: "a"}), "application/octet-stream")},
        ).json()["file"]["id"]
        b = self.client.post(
            "/api/files",
            files={"file": ("bb.ucs", ucs_bytes({2: "b"}), "application/octet-stream")},
        ).json()["file"]["id"]
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = lambda *a: None
            res = self.client.post("/api/batch/compare", json={"file_ids": [a, b]})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mock_open.called)


if __name__ == "__main__":
    unittest.main()
