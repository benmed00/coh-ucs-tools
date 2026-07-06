"""Tests for game profiles, streaming scan, rate limit, SGA locale scan."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


from coh_ucs_tools.profiles.game import classify_document, detect_profile, validate_against_profile
from coh_ucs_tools.core.parser import parse_text, scan_file_stats, write_file
from coh_ucs_tools.io.sga import scan_install_locale_archives
from coh_ucs_tools.web.rate_limit import check_rate_limit


def make_doc(entries: dict[int, str]):
    return parse_text("\r\n".join(f"{k}\t{v}" for k, v in entries.items()) + "\r\n")


class GameProfileTests(unittest.TestCase):
    def test_classify_coh1_high_keys(self) -> None:
        doc = make_doc({1: "a", 559200: "Normandy", 11_000_000: "high"})
        result = classify_document(doc)
        self.assertEqual(result["best_match"], "coh1")
        self.assertGreater(result["confidence"], 0.5)

    def test_validate_bom_warning(self) -> None:
        doc = make_doc({1: "x"})
        doc.has_bom = False
        val = validate_against_profile(doc, "coh1")
        self.assertTrue(any(i["code"] == "bom-missing" for i in val["issues"]))

    def test_detect_profile_returns_id(self) -> None:
        doc = make_doc({100: "test"})
        self.assertIn(detect_profile(doc), ("coh1", "coh2", "dow1", "dow2"))


class ScanFileStatsTests(unittest.TestCase):
    def test_scan_matches_parse_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.ucs"
            write_file(path, [(1, "a"), (2, "b"), (99, "z")])
            stats = scan_file_stats(path)
            self.assertEqual(stats["keys"], 3)
            self.assertEqual(stats["min_key"], 1)
            self.assertEqual(stats["max_key"], 99)


class RateLimitTests(unittest.TestCase):
    def test_in_memory_allows_first_hit(self) -> None:
        allowed, reason = check_rate_limit("127.0.0.99", upload=False)
        self.assertTrue(allowed)
        self.assertIsNone(reason)


class SgaLocaleScanTests(unittest.TestCase):
    def test_empty_dir_returns_no_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(scan_install_locale_archives(tmp), [])


if __name__ == "__main__":
    unittest.main()
