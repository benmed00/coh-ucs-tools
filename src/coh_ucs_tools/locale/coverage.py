"""Per-locale coverage tables vs the Russian CE reference key set.

Scans known ``*.complete.ucs`` / MT builds on disk and reports keys, coverage %,
missing counts, placeholder counts, and compressed gap ranges.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from coh_ucs_tools.config.paths import REPORTS_DIR
from coh_ucs_tools.core.merge import PLACEHOLDER
from coh_ucs_tools.core.parser import UcsDocument, parse_file
from coh_ucs_tools.analysis.stats import Comparison, compress_ranges

logger = logging.getLogger(__name__)

DEFAULT_REFERENCE = Path(
    r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale\Russian\RelicCOH.Russian.ucs"
)

LOCALE_TARGETS: list[dict] = [
    {"code": "EN", "name": "English", "path": Path("RelicCOH.English.complete.ucs")},
    {"code": "FR", "name": "French", "path": Path("RelicCOH.French.complete.ucs")},
    {"code": "DE", "name": "German", "path": Path("RelicCOH.German.complete.ucs")},
    {"code": "ES", "name": "Spanish", "path": Path("RelicCOH.Spanish.complete.ucs")},
    {"code": "IT", "name": "Italian", "path": Path("RelicCOH.Italian.complete.ucs")},
    {"code": "PL", "name": "Polish", "path": Path("RelicCOH.Polish.complete.ucs")},
    {"code": "AR", "name": "Arabic (MT)", "path": Path("RelicCOH.Arabic.MT.ucs")},
]


@dataclass(frozen=True)
class LocaleCoverageRow:
    code: str
    name: str
    path: str
    found: bool
    keys: int
    reference_keys: int
    common_keys: int
    missing_vs_reference: int
    extra_keys: int
    coverage_percent: float
    placeholders: int
    empty_values: int
    gap_ranges: list[str]


def _count_placeholders(doc: UcsDocument) -> int:
    return sum(
        1 for v in doc.entries.values()
        if v == PLACEHOLDER or "<MISSING>" in v
    )


def analyze_locale(
    reference: UcsDocument,
    *,
    code: str,
    name: str,
    path: Path,
) -> LocaleCoverageRow:
    ref_keys = len(reference.entries)
    if not path.is_file():
        return LocaleCoverageRow(
            code=code, name=name, path=str(path), found=False,
            keys=0, reference_keys=ref_keys, common_keys=0,
            missing_vs_reference=ref_keys, extra_keys=0,
            coverage_percent=0.0, placeholders=0, empty_values=0,
            gap_ranges=compress_ranges(reference.keys) if ref_keys else [],
        )

    doc = parse_file(path)
    comp = Comparison(russian=reference, english=doc)
    missing = comp.missing_in_english
    cov = round(100.0 * len(comp.common_keys) / ref_keys, 2) if ref_keys else 0.0
    return LocaleCoverageRow(
        code=code,
        name=name,
        path=str(path.resolve()),
        found=True,
        keys=len(doc.entries),
        reference_keys=ref_keys,
        common_keys=len(comp.common_keys),
        missing_vs_reference=len(missing),
        extra_keys=len(comp.missing_in_russian),
        coverage_percent=cov,
        placeholders=_count_placeholders(doc),
        empty_values=sum(1 for v in doc.entries.values() if v == ""),
        gap_ranges=compress_ranges(missing),
    )


def build_coverage_table(
    reference_path: Path | str | None = None,
    targets: Iterable[dict] | None = None,
) -> dict:
    """Build a multi-locale coverage table against the Russian CE reference."""
    ref_path = Path(reference_path) if reference_path else DEFAULT_REFERENCE
    specs = list(targets) if targets is not None else LOCALE_TARGETS

    if not ref_path.is_file():
        return {
            "reference_path": str(ref_path),
            "reference_keys": 0,
            "reference_found": False,
            "locales": [],
            "error": f"Reference not found: {ref_path}",
        }

    reference = parse_file(ref_path)
    rows = [
        analyze_locale(
            reference,
            code=spec["code"],
            name=spec["name"],
            path=Path(spec["path"]),
        )
        for spec in specs
    ]
    return {
        "reference_path": str(ref_path.resolve()),
        "reference_keys": len(reference.entries),
        "reference_found": True,
        "locales": [_row_to_dict(r) for r in rows],
    }


def _row_to_dict(row: LocaleCoverageRow) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "path": row.path,
        "found": row.found,
        "keys": row.keys,
        "reference_keys": row.reference_keys,
        "common_keys": row.common_keys,
        "missing_vs_reference": row.missing_vs_reference,
        "extra_keys": row.extra_keys,
        "coverage_percent": row.coverage_percent,
        "placeholders": row.placeholders,
        "empty_values": row.empty_values,
        "gap_ranges": row.gap_ranges,
        "gap_range_count": len(row.gap_ranges),
    }


def coverage_to_csv(table: dict) -> str:
    """Serialize coverage table as CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "code", "name", "found", "keys", "reference_keys", "common_keys",
        "missing_vs_reference", "extra_keys", "coverage_percent",
        "placeholders", "empty_values", "gap_range_count",
    ])
    for row in table.get("locales", []):
        writer.writerow([
            row["code"], row["name"], row["found"], row["keys"],
            row["reference_keys"], row["common_keys"], row["missing_vs_reference"],
            row["extra_keys"], row["coverage_percent"], row["placeholders"],
            row["empty_values"], row.get("gap_range_count", len(row.get("gap_ranges", []))),
        ])
    return buf.getvalue()


def write_coverage_report(
    out_dir: Path | str = REPORTS_DIR / "coverage",
    *,
    reference_path: Path | str | None = None,
) -> Path:
    """Write ``coverage.json``, ``coverage.csv``, and per-locale gap files."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    table = build_coverage_table(reference_path=reference_path)
    (out / "coverage.json").write_text(
        json.dumps(table, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (out / "coverage.csv").write_text(coverage_to_csv(table), encoding="utf-8")
    for row in table.get("locales", []):
        if row["found"] and row["gap_ranges"]:
            gap_file = out / f"missing_{row['code'].lower()}.txt"
            gap_file.write_text("\n".join(row["gap_ranges"]) + "\n", encoding="utf-8")
    logger.info("Coverage report written to %s", out.resolve())
    return out
