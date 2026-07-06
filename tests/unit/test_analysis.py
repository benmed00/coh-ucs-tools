"""Tests for ucs_analysis module."""

from __future__ import annotations

import unittest


from coh_ucs_tools.core.parser import parse_text
from coh_ucs_tools.analysis.diff import (
    compare_tokens,
    diff_entries,
    expand_ranges,
    fingerprint_file,
    fuzzy_search,
    lint_document,
    script_detect,
    subset_by_ranges,
    token_linter,
)


def doc(entries: dict[int, str]):
    return parse_text("\r\n".join(f"{k}\t{v}" for k, v in entries.items()) + "\r\n")


class AnalysisTests(unittest.TestCase):
    def test_diff_changed_and_missing(self):
        a = doc({1: "one", 2: "two"})
        b = doc({1: "ONE", 3: "three"})
        changed = diff_entries(a, b, "changed")
        self.assertEqual([r.key for r in changed], [1])
        missing = diff_entries(a, b, "missing")
        keys = {r.key for r in missing}
        self.assertEqual(keys, {2, 3})

    def test_token_linter_and_compare(self):
        issues = token_linter("Hello %1NAME% and %2%")
        self.assertEqual(issues, [])
        bad = token_linter("Broken %token")
        self.assertTrue(any(i.code == "unclosed-token" for i in bad))
        mismatch = compare_tokens("%1%", "%1% %2%")
        self.assertIsNotNone(mismatch)

    def test_script_detect(self):
        findings = script_detect("<MISSING>")
        codes = {f.code for f in findings}
        self.assertIn("missing-literal", codes)
        cyr = script_detect("\u041f\u0440\u0438\u0432\u0435\u0442")
        self.assertTrue(any(f.code == "cyrillic" for f in cyr))

    def test_subset_and_ranges(self):
        entries = {1: "a", 5: "b", 10: "c"}
        sub = subset_by_ranges(entries, ["1", "5-6"])
        self.assertEqual(sub, {1: "a", 5: "b"})
        self.assertEqual(expand_ranges(["2-3"]), {2, 3})

    def test_fuzzy_search(self):
        entries = {1: "Panzer IV Medium Tank", 2: "Sherman Tank"}
        hits = fuzzy_search("panzer medium", entries, threshold=0.4)
        self.assertTrue(hits)
        self.assertEqual(hits[0][0], 1)

    def test_fingerprint_bytes(self):
        from coh_ucs_tools.core.parser import BOM_LE
        raw = BOM_LE + "1\ttest\r\n".encode("utf-16-le")
        fp = fingerprint_file(raw)
        self.assertEqual(fp.encoding, "utf-16-le")
        self.assertTrue(fp.has_bom)
        self.assertEqual(fp.crlf_count, 1)

    def test_lint_document_summary(self):
        d = doc({1: "<MISSING>", 2: "ok %1%"})
        summary = lint_document(d)
        self.assertGreater(summary["entries_with_issues"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
