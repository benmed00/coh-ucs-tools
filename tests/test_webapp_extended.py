"""Extended API tests for new webapp endpoints."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import BOM_LE  # noqa: E402


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class ExtendedWebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")

        from fastapi.testclient import TestClient
        from webapp.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        cls._tmp.cleanup()

    def upload(self, name: str, entries: dict[int, str]) -> dict:
        res = self.client.post(
            "/api/files",
            files={"file": (name, ucs_bytes(entries), "application/octet-stream")},
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["file"]

    def test_diff_endpoint(self) -> None:
        a = self.upload("a.ucs", {1: "one", 2: "two"})
        b = self.upload("b.ucs", {1: "ONE", 3: "three"})
        res = self.client.get(f"/api/files/{a['id']}/diff/{b['id']}", params={"filter": "changed"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 1)
        self.assertEqual(res.json()["rows"][0]["key"], 1)

    def test_fingerprint(self) -> None:
        f = self.upload("fp.ucs", {1: "x"})
        res = self.client.get(f"/api/files/{f['id']}/fingerprint")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["sha256"]), 64)

    def test_languages_hub(self) -> None:
        res = self.client.get("/api/languages")
        self.assertEqual(res.status_code, 200)
        langs = res.json()["languages"]
        self.assertEqual(len(langs), 4)
        codes = {l["code"] for l in langs}
        self.assertEqual(codes, {"EN", "FR", "AR", "RU"})

    def test_bookmarks_crud(self) -> None:
        res = self.client.post("/api/bookmarks", json={"ids": [559200, 9419700]})
        self.assertEqual(res.status_code, 200)
        self.assertIn(559200, res.json()["ids"])
        res = self.client.delete("/api/bookmarks/559200")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(559200, res.json()["ids"])

    def test_merge_preview(self) -> None:
        t = self.upload("t.ucs", {1: "one"})
        s = self.upload("s.ucs", {1: "a", 2: "two", 3: "three"})
        res = self.client.post("/api/merge/preview", json={
            "target_id": t["id"], "source_id": s["id"], "mode": "placeholder", "limit": 2,
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total_would_add"], 2)
        self.assertEqual(len(body["preview"]), 2)

    def test_install_detect(self) -> None:
        res = self.client.get("/api/install/detect")
        self.assertEqual(res.status_code, 200)
        self.assertIn("candidates", res.json())
        self.assertIn("backup_command", res.json())

    def test_batch_compare(self) -> None:
        a = self.upload("ba.ucs", {1: "a"})
        b = self.upload("bb.ucs", {1: "b", 2: "c"})
        res = self.client.post("/api/batch/compare", json={"file_ids": [a["id"], b["id"]]})
        self.assertEqual(res.status_code, 200)
        job_id = res.json()["job_id"]
        zip_res = self.client.get(f"/api/batch/compare/{job_id}/zip")
        self.assertEqual(zip_res.status_code, 200)
        self.assertEqual(zip_res.headers["content-type"], "application/zip")

    def test_issues_and_csv(self) -> None:
        raw = BOM_LE + "1\ta\r\n1\tb\r\nbad\r\n".encode("utf-16-le")
        res = self.client.post("/api/files",
                               files={"file": ("bad.ucs", raw, "application/octet-stream")})
        fid = res.json()["file"]["id"]
        issues = self.client.get(f"/api/files/{fid}/issues").json()
        self.assertEqual(len(issues["duplicates"]), 1)
        csv_res = self.client.get(f"/api/files/{fid}/issues.csv")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("duplicate", csv_res.text)

    def test_global_search(self) -> None:
        f = self.upload("sr.ucs", {100: "Panzer IV"})
        res = self.client.get("/api/search/global", params={"q": "panzer", "file_ids": f["id"]})
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()["total"], 1)

    def test_timeline_and_glossary(self) -> None:
        self.assertEqual(self.client.get("/api/versions/timeline").status_code, 200)
        put = self.client.put("/api/glossary", json={"terms": {"Panzer": "Panzer"}})
        self.assertEqual(put.status_code, 200)
        get = self.client.get("/api/glossary")
        self.assertEqual(get.json()["terms"]["Panzer"], "Panzer")

    def test_patch_build(self) -> None:
        f = self.upload("patch.ucs", {100: "a", 200: "b", 300: "c"})
        res = self.client.post("/api/patch/build", json={"file_id": f["id"], "ranges": ["100-200"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["keys"], 2)

    def test_compare_ranges_heatmap(self) -> None:
        a = self.upload("ha.ucs", {1: "a", 1000: "b"})
        b = self.upload("hb.ucs", {2: "c"})
        res = self.client.get(f"/api/compare/{a['id']}/{b['id']}/ranges")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["a_missing"] or res.json()["b_missing"])

    def test_campaign_ranges(self) -> None:
        res = self.client.get("/api/campaigns/ranges")
        self.assertEqual(res.status_code, 200)
        self.assertIn("campaigns", res.json())

    def test_games_profiles(self) -> None:
        res = self.client.get("/api/games")
        self.assertEqual(res.status_code, 200)
        ids = [p["id"] for p in res.json()["profiles"]]
        self.assertIn("coh1", ids)

    def test_audit_csv_export(self) -> None:
        res = self.client.get("/api/audit/export.csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("action", res.text)

    def test_threeway_merge(self) -> None:
        base = self.upload("base.ucs", {1: "base"})
        a = self.upload("a.ucs", {1: "aaa", 2: "new"})
        b = self.upload("b.ucs", {1: "bbb", 3: "other"})
        res = self.client.post("/api/merge/threeway", json={
            "base": base["id"], "a": a["id"], "b": b["id"], "strategy": "prefer_a",
        })
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json()["keys"], 0)

    def test_community_hash_registry(self) -> None:
        sha = "a" * 64
        res = self.client.post("/api/community/hash", json={
            "sha256": sha, "key_count": 100, "label": "test",
        })
        self.assertEqual(res.status_code, 200)
        lst = self.client.get("/api/community/hashes")
        self.assertTrue(any(h["sha256"] == sha for h in lst.json()["hashes"]))

    def test_depot_fetch_instructions(self) -> None:
        res = self.client.post("/api/depot/fetch-instructions", json={"depot_id": 4565})
        self.assertEqual(res.status_code, 200)
        self.assertIn("DepotDownloader", res.json()["command"])

    def test_install_script(self) -> None:
        res = self.client.get("/api/install/script", params={"target": str(Path.home() / "test.ucs")})
        self.assertEqual(res.status_code, 200)
        self.assertIn("script", res.json())

    def test_projects_crud(self) -> None:
        res = self.client.post("/api/projects", json={"name": "QA workspace"})
        self.assertEqual(res.status_code, 200)
        lst = self.client.get("/api/projects")
        self.assertTrue(any(p["name"] == "QA workspace" for p in lst.json()["projects"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
