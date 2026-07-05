"""Wave 5: locale coverage tables, unified diff export, SGA CLI."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import BOM_LE, parse_file, parse_text, write_file
from locale_coverage import analyze_locale, build_coverage_table, coverage_to_csv, write_coverage_report
from ucs_analysis import export_unified_diff


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class LocaleCoverageTests(unittest.TestCase):
    def test_analyze_locale_missing_file(self) -> None:
        ref = parse_text("1\ta\r\n2\tb\r\n3\tc\r\n")
        row = analyze_locale(ref, code="FR", name="French", path=Path("nope.ucs"))
        self.assertFalse(row.found)
        self.assertEqual(row.missing_vs_reference, 3)

    def test_build_coverage_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = root / "ru.ucs"
            fr = root / "fr.ucs"
            write_file(ref, [(1, "a"), (2, "b"), (3, "c")])
            write_file(fr, [(1, "un"), (2, "deux")])
            ref_doc = parse_file(ref)
            row = analyze_locale(ref_doc, code="FR", name="French", path=fr)
            self.assertTrue(row.found)
            self.assertEqual(row.keys, 2)
            self.assertEqual(row.missing_vs_reference, 1)
            self.assertAlmostEqual(row.coverage_percent, 66.67)

    def test_write_coverage_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = root / "ru.ucs"
            write_file(ref, [(1, "x")])
            out = write_coverage_report(root / "report", reference_path=ref)
            self.assertTrue((out / "coverage.json").is_file())
            self.assertTrue((out / "coverage.csv").is_file())
            csv_text = coverage_to_csv(build_coverage_table(reference_path=ref))
            self.assertIn("code,name", csv_text.replace(" ", ""))


class UnifiedDiffTests(unittest.TestCase):
    def test_export_unified_diff_changed(self) -> None:
        a = parse_text("1\tone\r\n2\ttwo\r\n")
        b = parse_text("1\tONE\r\n2\ttwo\r\n3\tthree\r\n")
        diff = export_unified_diff(a, b, label_a="a", label_b="b", filters=("changed", "missing"))
        self.assertIn("--- a", diff)
        self.assertIn("+++ b", diff)
        self.assertIn("ONE", diff)


class CoverageWebAppTests(unittest.TestCase):
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

    def test_languages_coverage_endpoint(self) -> None:
        res = self.client.get("/api/languages/coverage")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("locales", body)
        self.assertGreaterEqual(len(body["locales"]), 7)

    def test_diff_udiff_endpoint(self) -> None:
        a = self.client.post(
            "/api/files",
            files={"file": ("a.ucs", ucs_bytes({1: "one", 2: "two"}), "application/octet-stream")},
        ).json()["file"]["id"]
        b = self.client.post(
            "/api/files",
            files={"file": ("b.ucs", ucs_bytes({1: "ONE", 3: "three"}), "application/octet-stream")},
        ).json()["file"]["id"]
        res = self.client.get(f"/api/files/{a}/diff/{b}/udiff")
        self.assertEqual(res.status_code, 200)
        self.assertIn("---", res.text)


if __name__ == "__main__":
    unittest.main()
