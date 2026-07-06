"""API tests for the web application (FastAPI TestClient).

Covers the full happy path: upload -> analyze (summary, entries, search,
validation) -> compare -> merge -> download, plus versions/tools/health and
the main error cases.

Run with:  python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


from coh_ucs_tools.core.parser import BOM_LE  # noqa: E402


def ucs_bytes(entries: dict[int, str]) -> bytes:
    """Build a syntactically valid UCS file in memory."""
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class WebAppTests(unittest.TestCase):
    """Spins up the app once with an isolated temp storage directory."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")

        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()  # run lifespan (store creation + version registry)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        cls._tmp.cleanup()

    # ------------------------------------------------------------ helpers
    def upload(self, name: str, entries: dict[int, str]) -> dict:
        res = self.client.post(
            "/api/files",
            files={"file": (name, ucs_bytes(entries), "application/octet-stream")},
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["file"]

    # -------------------------------------------------------------- tests
    def test_health(self) -> None:
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_upload_analyze_compare_merge_download_happy_path(self) -> None:
        english = self.upload("english.ucs", {1: "one", 3: "three"})
        russian = self.upload("russian.ucs", {1: "\u043e\u0434\u0438\u043d",
                                              2: "\u0434\u0432\u0430",
                                              3: "\u0442\u0440\u0438"})
        # upload summary
        self.assertEqual(english["keys"], 2)
        self.assertEqual(english["encoding"], "utf-16-le")
        self.assertTrue(english["has_bom"])
        self.assertEqual(english["newline"], "CRLF")

        # summary endpoint
        res = self.client.get(f"/api/files/{english['id']}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["keys"], 2)

        # entries + search
        res = self.client.get(f"/api/files/{russian['id']}/entries")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([e["key"] for e in res.json()["entries"]], [1, 2, 3])

        res = self.client.get(f"/api/files/{russian['id']}/entries",
                              params={"search": "\u0434\u0432\u0430"})
        self.assertEqual(res.json()["total"], 1)
        self.assertEqual(res.json()["entries"][0]["key"], 2)

        res = self.client.get(f"/api/files/{russian['id']}/entries",
                              params={"search": "^\u043e", "regex": "true"})
        self.assertEqual(res.json()["total"], 1)

        # validation
        res = self.client.get(f"/api/files/{english['id']}/validate")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # compare
        res = self.client.get("/api/compare",
                              params={"a": russian["id"], "b": english["id"]})
        self.assertEqual(res.status_code, 200)
        cmp_ = res.json()
        self.assertEqual(cmp_["union_keys"], 3)
        self.assertEqual(cmp_["common_keys"], 2)
        self.assertEqual(cmp_["b"]["missing_keys"], 1)
        self.assertEqual(cmp_["b"]["missing_ranges"], ["2"])
        self.assertEqual(cmp_["a"]["missing_ranges"], [])

        # merge (placeholder mode)
        res = self.client.post("/api/merge", json={
            "target_id": english["id"], "source_id": russian["id"],
            "mode": "placeholder",
        })
        self.assertEqual(res.status_code, 200, res.text)
        merged = res.json()
        self.assertEqual(merged["total_entries"], 3)
        self.assertEqual(merged["preserved"], 2)
        self.assertEqual(merged["added"], 1)
        self.assertTrue(merged["filename"].endswith(".merged.ucs"))

        # download and verify the merged bytes
        res = self.client.get(merged["download_url"])
        self.assertEqual(res.status_code, 200)
        self.assertIn("attachment", res.headers["content-disposition"])
        raw = res.content
        self.assertTrue(raw.startswith(BOM_LE))
        text = raw.decode("utf-16-le").lstrip("\ufeff")
        self.assertEqual(text, "1\tone\r\n2\t<MISSING>\r\n3\tthree\r\n")

    def test_merge_fill_from_source_copies_verbatim(self) -> None:
        target = self.upload("t.ucs", {1: "one"})
        source = self.upload("s.ucs", {1: "\u043e\u0434\u0438\u043d", 2: "\u0434\u0432\u0430"})
        res = self.client.post("/api/merge", json={
            "target_id": target["id"], "source_id": source["id"],
            "mode": "fill_from_source",
        })
        self.assertEqual(res.status_code, 200, res.text)
        raw = self.client.get(res.json()["download_url"]).content
        text = raw.decode("utf-16-le").lstrip("\ufeff")
        self.assertEqual(text, "1\tone\r\n2\t\u0434\u0432\u0430\r\n")

    def test_validation_reports_issues(self) -> None:
        raw = BOM_LE + "1\ta\r\n1\tb\r\n2\t\r\nbroken line\r\n".encode("utf-16-le")
        res = self.client.post("/api/files",
                               files={"file": ("bad.ucs", raw, "application/octet-stream")})
        file_id = res.json()["file"]["id"]
        val = self.client.get(f"/api/files/{file_id}/validate").json()
        self.assertFalse(val["ok"])
        codes = {i["code"] for i in val["issues"]}
        self.assertIn("duplicate-id", codes)
        self.assertIn("invalid-line", codes)
        self.assertIn("empty-value", codes)

    def test_delete_and_404(self) -> None:
        rec = self.upload("gone.ucs", {1: "x"})
        res = self.client.delete(f"/api/files/{rec['id']}")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get(f"/api/files/{rec['id']}").status_code, 404)
        self.assertEqual(self.client.delete("/api/files/nope").status_code, 404)

    def test_upload_rejects_empty_file(self) -> None:
        res = self.client.post("/api/files",
                               files={"file": ("empty.ucs", b"", "application/octet-stream")})
        self.assertEqual(res.status_code, 400)

    def test_invalid_regex_is_400(self) -> None:
        rec = self.upload("re.ucs", {1: "x"})
        res = self.client.get(f"/api/files/{rec['id']}/entries",
                              params={"search": "([", "regex": "true"})
        self.assertEqual(res.status_code, 400)

    def test_versions_and_tools_registries(self) -> None:
        res = self.client.get("/api/versions")
        self.assertEqual(res.status_code, 200)
        versions = res.json()["versions"]
        self.assertEqual(len(versions), 4)
        ids = {v["id"] for v in versions}
        self.assertIn("nsv-english", ids)
        # at least the repo-local files should be registered on this machine
        available = [v for v in versions if v["available"]]
        for v in available:
            self.assertGreater(v["keys"], 0)
            self.assertTrue(v["download_url"])

        res = self.client.get("/api/tools")
        tools = res.json()["tools"]
        self.assertGreaterEqual(len(tools), 6)
        self.assertTrue(all(t["url"].startswith("http") for t in tools))

    def test_openapi_and_docs_served(self) -> None:
        res = self.client.get("/openapi.json")
        self.assertEqual(res.status_code, 200)
        spec = res.json()
        self.assertEqual(spec["info"]["title"], "CoH UCS Tools")
        self.assertIn("/api/files", spec["paths"])
        self.assertEqual(self.client.get("/docs").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)


    def test_health_public_when_api_key_set(self) -> None:
        os.environ["UCS_API_KEY"] = "test-secret"
        try:
            res = self.client.get("/api/health")
            self.assertEqual(res.status_code, 200)
            denied = self.client.post(
                "/api/files",
                files={"file": ("x.ucs", ucs_bytes({1: "a"}), "application/octet-stream")},
            )
            self.assertEqual(denied.status_code, 401)
            ok = self.client.post(
                "/api/files",
                files={"file": ("x.ucs", ucs_bytes({1: "a"}), "application/octet-stream")},
                headers={"X-API-Key": "test-secret"},
            )
            self.assertEqual(ok.status_code, 201)
        finally:
            os.environ.pop("UCS_API_KEY", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
