"""Tests for build_french.py (search, union build, reporting)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


from coh_ucs_tools.locale.build import SearchHit, build_complete, pick_nsv_path
from coh_ucs_tools.locale.builders.french import search_local_french, write_french_report
from coh_ucs_tools.core.merge import PLACEHOLDER
from coh_ucs_tools.core.parser import parse_file, write_file


def make_ucs(path: Path, entries: dict[int, str]) -> Path:
    write_file(path, sorted(entries.items()))
    return path


class BuildFrenchTests(unittest.TestCase):
    def test_pick_nsv_prefers_downloads(self) -> None:
        hits = [
            SearchHit(r"C:\games\French\RelicCOH.French.ucs", "install"),
            SearchHit("downloads/RelicCOH.French.NSV.ucs", "downloads"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            nsv = make_ucs(Path(tmp) / "RelicCOH.French.NSV.ucs", {1: "un"})
            picked = pick_nsv_path(
                [SearchHit(str(nsv), "downloads/: *French*")],
                None,
                "french",
            )
            self.assertEqual(picked, nsv)

    def test_build_complete_unions_thq_and_fills_russian_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nsv = parse_file(make_ucs(root / "nsv.ucs", {1: "un", 2: "deux"}))
            thq = parse_file(make_ucs(root / "thq.ucs", {1: "un", 99: "legacy"}))
            russian = parse_file(make_ucs(root / "ru.ucs", {1: "один", 2: "два", 3: "три"}))
            out = root / "complete.ucs"
            info = build_complete(nsv, thq, russian, out)
            doc = parse_file(out)
            self.assertEqual(doc.entries[1], "un")
            self.assertEqual(doc.entries[2], "deux")
            self.assertEqual(doc.entries[99], "legacy")
            self.assertEqual(doc.entries[3], PLACEHOLDER)
            self.assertEqual(info["legacy_only_count"], 1)
            self.assertEqual(info["russian_gap_placeholders"], 1)

    def test_write_french_report_creates_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ru = make_ucs(root / "ru.ucs", {1: "a"})
            fr = make_ucs(root / "fr.ucs", {1: "un"})
            report_dir = root / "report" / "french"
            import coh_ucs_tools.locale.builders.french as bf
            from dataclasses import replace

            original = bf.CONFIG
            try:
                bf.CONFIG = replace(original, report_dir=report_dir)
                write_french_report(
                    search_hits=[],
                    nsv_path=fr,
                    thq_path=None,
                    russian_path=ru,
                    english_complete_path=None,
                    output_path=fr,
                    build_info={"total_keys": 1},
                    recovery_notes=[],
                )
            finally:
                bf.CONFIG = original
            stats = json.loads((report_dir / "statistics.json").read_text(encoding="utf-8"))
            self.assertTrue(stats["recovery"]["official_french_found"])
            self.assertIn("nsv", stats)


class SearchFrenchTests(unittest.TestCase):
    def test_search_local_french_returns_list(self) -> None:
        hits = search_local_french()
        self.assertIsInstance(hits, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
