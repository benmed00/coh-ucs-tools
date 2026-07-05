"""Tests for parser encoding heuristics and patch apply."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import BOM_LE, parse_bytes, parse_file_chunked, probe_utf16le_ucs, write_file
from ucs_analysis import apply_patch_overlay
from duplicate_probe import build_duplicate_probe_bytes, write_duplicate_probe
from parser import parse_file


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class EncodingProbeTests(unittest.TestCase):
    def test_valid_bomless_ucs_probes_true(self) -> None:
        raw = ucs_bytes({1: "one", 2: "two", 3: "three"})[2:]  # strip BOM
        self.assertTrue(probe_utf16le_ucs(raw))

    def test_random_binary_probes_false(self) -> None:
        self.assertFalse(probe_utf16le_ucs(os.urandom(512)))

    def test_random_binary_not_parsed_as_ucs(self) -> None:
        doc = parse_bytes(os.urandom(800))
        self.assertEqual(len(doc.entries), 0)

    def test_bomless_ucs_parses(self) -> None:
        raw = ucs_bytes({100: "test", 200: "more"})[2:]
        doc = parse_bytes(raw)
        self.assertEqual(doc.entries[100], "test")
        self.assertFalse(doc.has_bom)


class PatchApplyTests(unittest.TestCase):
    def test_overlay_changed_and_added(self) -> None:
        from parser import parse_text

        base = parse_text("1\tone\r\n2\ttwo\r\n")
        patch = parse_text("2\tTWO\r\n3\tthree\r\n")
        merged, changed, added = apply_patch_overlay(base, patch)
        self.assertEqual(merged[2], "TWO")
        self.assertEqual(merged[3], "three")
        self.assertEqual(changed, [2])
        self.assertEqual(added, [3])


class DuplicateProbeTests(unittest.TestCase):
    def test_probe_has_duplicate_lines(self) -> None:
        raw = build_duplicate_probe_bytes()
        text = raw.decode("utf-16-le").lstrip("\ufeff")
        self.assertEqual(text.count("99999001"), 2)

    def test_write_probe_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_duplicate_probe(Path(tmp) / "probe.ucs")
            doc = parse_file(path)
            self.assertEqual(doc.entries[99999001], "DUPLICATE_PROBE_SECOND")


class ChunkedParserTests(unittest.TestCase):
    def test_invalid_line_in_chunked_parse(self) -> None:
        raw = BOM_LE + "1\tok\r\nbadline\r\n2\ttwo\r\n".encode("utf-16-le")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inv.ucs"
            path.write_bytes(raw)
            doc = parse_file_chunked(path)
            self.assertEqual(len(doc.invalid_lines), 1)
            self.assertEqual(doc.entries[1], "ok")


if __name__ == "__main__":
    unittest.main()
