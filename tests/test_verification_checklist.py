"""Tests for verification_checklist.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from merge import PLACEHOLDER
from parser import write_file
from verification_checklist import run_checklist, run_checklist_file


def make_ucs(path: Path, entries: dict[int, str]) -> Path:
    write_file(path, sorted(entries.items()))
    return path


class VerificationChecklistTests(unittest.TestCase):
    def test_passes_complete_english_spot_ids(self) -> None:
        entries = {
            559200: "Invasion of Normandy",
            9419700: "Causeway",
            9391740: "Falaise Pocket",
            713520: "MULTIPLAYER",
            713521: "OPTIONS",
            713530: "CONTINUE",
            713540: "SELECT MISSION",
            713544: "OPERATIONS",
            713525: "To unlock Operations, please purchase Company of Heroes: Tales of Valor",
            1050: "New Army",
            5000: "Back",
            17000: "Delete Profile",
            250: "Arial",
            1: "%1X%.%2Y%",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = make_ucs(Path(tmp) / "test.ucs", entries)
            report = run_checklist_file(path)
        self.assertTrue(report["ok"])
        self.assertEqual(report["failed"], 0)

    def test_fails_missing_and_placeholder(self) -> None:
        from parser import parse_file

        with tempfile.TemporaryDirectory() as tmp:
            path = make_ucs(Path(tmp) / "bad.ucs", {559200: PLACEHOLDER, 1050: "Army"})
            doc = parse_file(path)
            report = run_checklist(doc)
        self.assertFalse(report["ok"])
        self.assertGreater(report["failed"], 0)
        row = next(r for r in report["items"] if r["key"] == 559200)
        self.assertEqual(row["status"], "fail")


if __name__ == "__main__":
    unittest.main()
