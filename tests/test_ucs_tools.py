"""Unit tests for the UCS toolkit (parser, writer, validator, merge, sorting).

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from merge import PLACEHOLDER, merge_and_write, merge_documents
from parser import (BOM_LE, UcsDocument, parse_bytes, parse_file, parse_text,
                    serialize, write_file)
from ucs_stats import Comparison, compress_ranges, generate_report
from translate import protect_tokens, restore_tokens
from validator import Severity, validate


def make_bytes(text: str) -> bytes:
    return BOM_LE + text.encode("utf-16-le")


def make_doc(entries: dict[int, str], path: Path | None = None) -> UcsDocument:
    doc = parse_text("\r\n".join(f"{k}\t{v}" for k, v in entries.items()) + "\r\n")
    doc.path = path
    return doc


class ParserTests(unittest.TestCase):
    def test_parses_bom_utf16le_crlf(self):
        doc = parse_bytes(make_bytes("1\tone\r\n250\tnormal\r\n"))
        self.assertEqual(doc.entries, {1: "one", 250: "normal"})
        self.assertEqual(doc.encoding, "utf-16-le")
        self.assertTrue(doc.has_bom)
        self.assertEqual(doc.newline, "\r\n")
        self.assertTrue(doc.trailing_newline)

    def test_value_may_contain_tabs(self):
        doc = parse_text("5\ta\tb\tc\r\n")
        self.assertEqual(doc.entries[5], "a\tb\tc")

    def test_empty_value_is_kept(self):
        doc = parse_text("7\t\r\n")
        self.assertEqual(doc.entries[7], "")

    def test_duplicate_last_occurrence_wins(self):
        doc = parse_text("1\tfirst\r\n1\tsecond\r\n")
        self.assertEqual(doc.entries[1], "second")
        self.assertEqual(doc.duplicates, {1: [1, 2]})

    def test_invalid_lines_are_reported_not_dropped_silently(self):
        doc = parse_text("no tab here\r\nabc\tvalue\r\n1\tok\r\n")
        self.assertEqual(doc.entries, {1: "ok"})
        self.assertEqual(len(doc.invalid_lines), 2)
        reasons = [line.reason for line in doc.invalid_lines]
        self.assertIn("no tab separator", reasons[0])
        self.assertIn("non-numeric key", reasons[1])

    def test_missing_trailing_newline(self):
        doc = parse_text("1\tone\r\n2\ttwo")
        self.assertEqual(doc.entries, {1: "one", 2: "two"})
        self.assertFalse(doc.trailing_newline)

    def test_utf16be_bom_detected(self):
        raw = b"\xfe\xff" + "1\tone\r\n".encode("utf-16-be")
        doc = parse_bytes(raw)
        self.assertEqual(doc.encoding, "utf-16-be")
        self.assertEqual(doc.entries, {1: "one"})

    def test_unicode_values_roundtrip(self):
        doc = parse_bytes(make_bytes("250\t\u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e\r\n"))
        self.assertEqual(doc.entries[250], "\u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e")


class WriterTests(unittest.TestCase):
    def test_serialize_format(self):
        text = serialize([(1, "one"), (2, "two")])
        self.assertEqual(text, "1\tone\r\n2\ttwo\r\n")

    def test_write_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.ucs"
            write_file(path, [(2, "b"), (1, "\u0430")])
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(BOM_LE))
            doc = parse_file(path)
            self.assertEqual(doc.entries, {2: "b", 1: "\u0430"})

    def test_write_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.ucs"
            write_file(path, [(1, "a")])
            with self.assertRaises(FileExistsError):
                write_file(path, [(1, "b")])
            write_file(path, [(1, "b")], overwrite=True)  # explicit opt-in works


class ValidatorTests(unittest.TestCase):
    def test_clean_document_is_ok(self):
        result = validate(make_doc({1: "a", 2: "b"}))
        self.assertTrue(result.ok)
        self.assertEqual(result.issues, [])

    def test_duplicates_are_errors(self):
        doc = parse_text("1\ta\r\n1\tb\r\n")
        result = validate(doc)
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].code, "duplicate-id")

    def test_empty_values_are_warnings(self):
        result = validate(make_doc({1: ""}))
        self.assertTrue(result.ok)
        self.assertEqual(result.warnings[0].code, "empty-value")

    def test_control_characters_flagged(self):
        result = validate(make_doc({1: "bad\x00value"}))
        self.assertEqual(result.errors[0].code, "bad-character")

    def test_lone_surrogate_flagged(self):
        result = validate(make_doc({1: "x" + chr(0xD800)}))
        self.assertEqual(result.errors[0].code, "bad-character")
        self.assertIn("surrogate", result.errors[0].message)

    def test_missing_ids_against_reference(self):
        result = validate(make_doc({1: "a"}), reference=make_doc({1: "a", 2: "b"}))
        missing = [i for i in result.issues if i.code == "missing-id"]
        self.assertEqual([i.key for i in missing], [2])
        self.assertIs(missing[0].severity, Severity.WARNING)

    def test_invalid_lines_are_errors(self):
        result = validate(parse_text("garbage line\r\n"))
        self.assertEqual(result.errors[0].code, "invalid-line")


class RangeTests(unittest.TestCase):
    def test_compress_ranges(self):
        self.assertEqual(compress_ranges([1, 2, 3, 7, 9, 10]), ["1-3", "7", "9-10"])

    def test_compress_single_and_empty(self):
        self.assertEqual(compress_ranges([]), [])
        self.assertEqual(compress_ranges([5]), ["5"])

    def test_compress_unsorted_input(self):
        self.assertEqual(compress_ranges([10, 9, 7, 3, 2, 1]), ["1-3", "7", "9-10"])


class ComparisonTests(unittest.TestCase):
    def test_missing_sets(self):
        comp = Comparison(russian=make_doc({1: "a", 2: "b", 3: "c"}),
                          english=make_doc({2: "B", 4: "D"}))
        self.assertEqual(comp.missing_in_english, [1, 3])
        self.assertEqual(comp.missing_in_russian, [4])
        self.assertEqual(comp.common_keys, [2])

    def test_statistics_coverage(self):
        comp = Comparison(russian=make_doc({1: "a", 2: "b", 3: "c", 4: "d"}),
                          english=make_doc({1: "A", 2: "B"}))
        stats = comp.statistics()
        self.assertEqual(stats["union_keys"], 4)
        self.assertEqual(stats["english"]["coverage_percent"], 50.0)
        self.assertEqual(stats["russian"]["coverage_percent"], 100.0)
        self.assertEqual(stats["english"]["missing_keys"], 2)

    def test_generate_report_files(self):
        comp = Comparison(russian=make_doc({1: "a", 2: "b"}), english=make_doc({2: "B"}))
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_report(comp, Path(tmp) / "report")
            for name in ("russian_keys.txt", "english_keys.txt", "missing_in_english.txt",
                         "missing_in_russian.txt", "duplicate_keys.txt",
                         "invalid_lines.txt", "statistics.json"):
                self.assertTrue((out / name).exists(), name)
            self.assertEqual((out / "missing_in_english.txt").read_text(encoding="utf-8").strip(), "1")


class MergeTests(unittest.TestCase):
    def test_merge_adds_placeholders_only(self):
        english = make_doc({1: "one", 3: "three"})
        russian = make_doc({1: "\u043e\u0434\u0438\u043d", 2: "\u0434\u0432\u0430", 3: "\u0442\u0440\u0438"})
        result = merge_documents(english, russian)
        self.assertEqual(result.entries[1], "one")  # never replaced
        self.assertEqual(result.entries[2], PLACEHOLDER)  # never translated
        self.assertEqual(result.added_placeholders, [2])
        self.assertEqual(result.preserved, 2)

    def test_merge_write_is_sorted_and_preserves_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            english = make_doc({30: "c", 1: "a"})
            russian = make_doc({2: "\u0431"})
            out = Path(tmp) / "merged.ucs"
            result = merge_and_write(english, russian, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(BOM_LE))
            text = raw.decode("utf-16-le")[1:]
            self.assertEqual(text, f"1\ta\r\n2\t{PLACEHOLDER}\r\n30\tc\r\n")
            self.assertEqual(result.output_path, out)

    def test_merge_fill_from_source_copies_verbatim(self):
        english = make_doc({1: "one"})
        russian = make_doc({1: "\u043e\u0434\u0438\u043d", 2: "\u0434\u0432\u0430"})
        result = merge_documents(english, russian, fill_from_source=True)
        self.assertEqual(result.entries[1], "one")  # target still wins
        self.assertEqual(result.entries[2], "\u0434\u0432\u0430")  # copied, not translated
        self.assertEqual(result.added_placeholders, [2])

    def test_merge_refuses_to_overwrite_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "RelicCOH.English.ucs"
            write_file(original, [(1, "one")])
            english = parse_file(original)
            russian = make_doc({2: "two"})
            with self.assertRaises(ValueError):
                merge_and_write(english, russian, original)
            self.assertEqual(parse_file(original).entries, {1: "one"})  # untouched


class SortingTests(unittest.TestCase):
    def test_keys_sorted_numerically_not_lexically(self):
        doc = make_doc({100: "a", 20: "b", 3: "c"})
        self.assertEqual(doc.keys, [3, 20, 100])
        self.assertEqual([k for k, _ in doc.sorted_entries()], [3, 20, 100])


class TokenProtectionTests(unittest.TestCase):
    def test_protect_and_restore_tokens(self):
        original = "Player %1PLAYERNAME% joined. Score: %2%."
        protected, tokens = protect_tokens(original)
        self.assertEqual(tokens, ["%1PLAYERNAME%", "%2%"])
        self.assertNotIn("%1PLAYERNAME%", protected)
        self.assertEqual(restore_tokens(protected, tokens), original)

    def test_protect_leaves_plain_text_unchanged(self):
        protected, tokens = protect_tokens("Invasion of Normandy")
        self.assertEqual(protected, "Invasion of Normandy")
        self.assertEqual(tokens, [])

    def test_restore_is_order_sensitive(self):
        text = "⟦MT0⟧ says hi to ⟦MT1⟧"
        restored = restore_tokens(text, ["%1NAME%", "%2NAME%"])
        self.assertEqual(restored, "%1NAME% says hi to %2NAME%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
