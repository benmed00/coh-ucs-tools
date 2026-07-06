"""Tests for Phase 1+ extensions: ucs_stats rename, validator rules, po_io, merge, db."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


from coh_ucs_tools.core.merge import PLACEHOLDER, merge_threeway
from coh_ucs_tools.core.parser import parse_text
from coh_ucs_tools.io.po import export_po, import_po
from coh_ucs_tools.tools.translate import compare, _normalize
from coh_ucs_tools.analysis.diff import campaign_ranges
from coh_ucs_tools.core.validator import validate


def make_doc(entries: dict[int, str]):
    doc = parse_text("\r\n".join(f"{k}\t{v}" for k, v in entries.items()) + "\r\n")
    return doc


class ValidatorExtensionTests(unittest.TestCase):
    def test_missing_literal_warning(self):
        result = validate(make_doc({1: PLACEHOLDER}))
        codes = [i.code for i in result.warnings]
        self.assertIn("missing-literal", codes)

    def test_cyrillic_in_latin_locale(self):
        result = validate(make_doc({1: "Привет"}), locale="english")
        self.assertTrue(any(i.code == "cyrillic-in-latin-locale" for i in result.warnings))

    def test_token_parity_with_reference(self):
        a = make_doc({1: "Hello %1%"})
        b = make_doc({1: "Hello %1% %2%"})
        result = validate(a, reference=b)
        self.assertTrue(any(i.code == "token-parity" for i in result.warnings))


class TranslateGlossaryTests(unittest.TestCase):
    def test_glossary_normalization(self):
        text = "Panzer squad advances"
        norm = _normalize(text, {"panzer": "tank", "squad": "section"})
        self.assertIn("tank", norm)
        self.assertIn("section", norm)

    def test_autojunk_false_in_compare(self):
        cache = {"1": "hello world"}
        rows = compare(cache, {1: "x"}, {1: "hello world"}, [1])
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(rows[0].similarity, 0.9)


class PoIoTests(unittest.TestCase):
    def test_roundtrip_po(self):
        doc = make_doc({1: "one", 2: "two %1%"})
        po = export_po(doc)
        entries = import_po(po)
        self.assertEqual(entries[1], "one")
        self.assertEqual(entries[2], "two %1%")

    def test_roundtrip_tmx(self):
        from coh_ucs_tools.io.po import export_tmx, import_tmx

        doc = make_doc({42: "hello", 99: "world %1%"})
        tmx = export_tmx(doc, source_lang="en", target_lang="de")
        entries = import_tmx(tmx)
        self.assertEqual(entries[42], "hello")
        self.assertEqual(entries[99], "world %1%")


class ThreewayMergeTests(unittest.TestCase):
    def test_prefer_a_strategy(self):
        base = make_doc({1: "base"})
        a = make_doc({1: "from_a", 2: "new_a"})
        b = make_doc({1: "from_b", 3: "new_b"})
        result = merge_threeway(base, a, b, strategy="prefer_a")
        self.assertEqual(result.entries[1], "from_a")
        self.assertEqual(result.entries[2], "new_a")
        self.assertEqual(result.entries[3], "new_b")

    def test_manual_conflicts(self):
        base = make_doc({1: "base"})
        a = make_doc({1: "aaa"})
        b = make_doc({1: "bbb"})
        result = merge_threeway(base, a, b, strategy="manual_conflicts")
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].key, 1)


class CampaignRangesTests(unittest.TestCase):
    def test_ranges_present(self):
        ranges = campaign_ranges()
        self.assertIn("base", ranges)
        self.assertIn("tales_of_valor", ranges)


class DatabaseTests(unittest.TestCase):
    def test_db_init_and_glossary(self):
        from coh_ucs_tools.web.db import Database
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.execute(
                "INSERT INTO glossary(term, replacement, updated_at) VALUES (?,?,?)",
                ("squad", "section", 1.0),
            )
            row = db.fetchone("SELECT replacement FROM glossary WHERE term=?", ("squad",))
            self.assertEqual(row["replacement"], "section")
            db.close()


class GameProfilesTests(unittest.TestCase):
    def test_list_profiles(self):
        from coh_ucs_tools.profiles.game import list_profiles
        profiles = list_profiles()
        ids = [p["id"] for p in profiles]
        self.assertIn("coh1", ids)
        self.assertIn("coh2", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
