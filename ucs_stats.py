"""Comparison statistics and report generation for two UCS documents.

Produces the ``report/`` directory:

* ``russian_keys.txt`` / ``english_keys.txt`` - all keys, sorted
* ``missing_in_english.txt`` / ``missing_in_russian.txt`` - missing IDs,
  compressed into ranges (e.g. ``559200-559650``)
* ``duplicate_keys.txt`` - duplicated IDs with their line numbers
* ``invalid_lines.txt`` - structurally broken lines
* ``statistics.json`` - machine-readable summary
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from parser import UcsDocument

logger = logging.getLogger(__name__)

REPORT_DIR = Path("report")


def compress_ranges(keys: Iterable[int]) -> list[str]:
    """Collapse sorted integers into range strings.

    ``[1, 2, 3, 7, 9, 10]`` becomes ``['1-3', '7', '9-10']``.
    """
    ranges: list[str] = []
    start = end = None
    for key in sorted(keys):
        if start is None:
            start = end = key
        elif key == end + 1:
            end = key
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = key
    if start is not None:
        ranges.append(f"{start}-{end}" if start != end else str(start))
    return ranges


@dataclass(frozen=True)
class Comparison:
    """Result of comparing two UCS documents."""

    russian: UcsDocument
    english: UcsDocument

    @property
    def missing_in_english(self) -> list[int]:
        return sorted(self.russian.entries.keys() - self.english.entries.keys())

    @property
    def missing_in_russian(self) -> list[int]:
        return sorted(self.english.entries.keys() - self.russian.entries.keys())

    @property
    def common_keys(self) -> list[int]:
        return sorted(self.russian.entries.keys() & self.english.entries.keys())

    def statistics(self) -> dict:
        ru, en = self.russian, self.english
        union = len(ru.entries.keys() | en.entries.keys())

        def side(doc: UcsDocument, missing: Sequence[int]) -> dict:
            return {
                "file": str(doc.path) if doc.path else None,
                "total_keys": len(doc.entries),
                "duplicated_keys": len(doc.duplicates),
                "invalid_lines": len(doc.invalid_lines),
                "empty_values": sum(1 for v in doc.entries.values() if v == ""),
                "missing_keys": len(missing),
                "coverage_percent": round(100.0 * len(doc.entries) / union, 2) if union else 100.0,
            }

        return {
            "union_keys": union,
            "common_keys": len(self.common_keys),
            "russian": side(ru, self.missing_in_russian),
            "english": side(en, self.missing_in_english),
        }


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote %s", path)


def generate_report(comparison: Comparison, out_dir: Path | str = REPORT_DIR) -> Path:
    """Write the full report directory and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ru, en = comparison.russian, comparison.english

    _write_lines(out / "russian_keys.txt", (str(k) for k in ru.keys))
    _write_lines(out / "english_keys.txt", (str(k) for k in en.keys))
    _write_lines(out / "missing_in_english.txt", compress_ranges(comparison.missing_in_english) or ["(none)"])
    _write_lines(out / "missing_in_russian.txt", compress_ranges(comparison.missing_in_russian) or ["(none)"])

    dup_lines = []
    for label, doc in (("russian", ru), ("english", en)):
        for key, line_numbers in sorted(doc.duplicates.items()):
            dup_lines.append(f"{label}\t{key}\tlines {', '.join(map(str, line_numbers))}")
    _write_lines(out / "duplicate_keys.txt", dup_lines or ["(none)"])

    invalid = []
    for label, doc in (("russian", ru), ("english", en)):
        for line in doc.invalid_lines:
            invalid.append(f"{label}\tline {line.line_number}\t{line.reason}\t{line.raw[:120]}")
    _write_lines(out / "invalid_lines.txt", invalid or ["(none)"])

    stats = comparison.statistics()
    (out / "statistics.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Report written to %s", out.resolve())
    return out
