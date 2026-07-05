"""Tests for locale_build, build_german, build_spanish."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_german import CONFIG as GERMAN_CONFIG
from locale_build import LocaleConfig, build_complete, pick_nsv_path, SearchHit, write_locale_report
from merge import PLACEHOLDER
from parser import parse_file, write_file


def make_ucs(path: Path, entries: dict[int, str]) -> Path:
    write_file(path, sorted(entries.items()))
    return path


class LocaleBuildTests(unittest.TestCase):
    def test_pick_nsv_prefers_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nsv = make_ucs(Path(tmp) / "RelicCOH.German.NSV.ucs", {1: "eins"})
            picked = pick_nsv_path(
                [SearchHit(str(nsv), "downloads")],
                None,
                "german",
            )
            self.assertEqual(picked, nsv)

    def test_build_complete_fills_russian_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nsv = parse_file(make_ucs(root / "nsv.ucs", {1: "eins", 2: "zwei"}))
            russian = parse_file(make_ucs(root / "ru.ucs", {1: "один", 2: "два", 3: "три"}))
            out = root / "complete.ucs"
            info = build_complete(nsv, None, russian, out)
            doc = parse_file(out)
            self.assertEqual(doc.entries[3], PLACEHOLDER)
            self.assertEqual(info["russian_gap_placeholders"], 1)

    def test_write_locale_report_german(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ru = make_ucs(root / "ru.ucs", {1: "a"})
            de = make_ucs(root / "de.ucs", {1: "eins"})
            report_dir = root / "report" / "german"
            cfg = LocaleConfig(
                language="german",
                language_title="German",
                ucs_basename="RelicCOH.German.ucs",
                search_patterns=("*German*",),
                default_nsv=root / "x.ucs",
                default_output=root / "out.ucs",
                report_dir=report_dir,
                depot_app_id=4560,
                depot_id=4564,
                depot_lang="german",
                web_search_note="test",
            )
            write_locale_report(
                cfg,
                search_hits=[],
                nsv_path=de,
                thq_path=None,
                russian_path=ru,
                english_complete_path=None,
                output_path=de,
                build_info={"total_keys": 1},
                recovery_notes=[],
            )
            stats = json.loads((report_dir / "statistics.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["language"], "german")
            self.assertTrue(stats["recovery"]["official_german_found"])


if __name__ == "__main__":
    unittest.main()
