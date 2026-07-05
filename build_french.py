"""Build official French ``RelicCOH.French.complete.ucs`` from recovered sources.

CoH1 **was** officially released in French. This script searches local installs
and ``downloads/`` for the official NSV/Legacy French UCS, optionally unions
legacy-only THQ retail keys, fills any remaining Russian CE gaps with
``<MISSING>`` (never machine-translates), and writes ``report/french/``.

Usage::

    python build_french.py --search-only          # document local search only
    python build_french.py --nsv path/to/French.ucs   # build from a recovered file
    python build_french.py                        # auto-detect NSV + build
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from merge import PLACEHOLDER, merge_and_write, merge_documents
from parser import UcsDocument, parse_file
from ucs_stats import Comparison, compress_ranges, generate_report
from validator import validate

logger = logging.getLogger(__name__)

DEFAULT_RUSSIAN = Path(
    r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale\Russian\RelicCOH.Russian.ucs"
)
DEFAULT_ENGLISH_COMPLETE = Path("RelicCOH.English.complete.ucs")
DEFAULT_NSV = Path("downloads/RelicCOH.French.NSV.ucs")
DEFAULT_OUTPUT = Path("RelicCOH.French.complete.ucs")
REPORT_DIR = Path("report/french")

CE_LOCALE = Path(r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale")
STEAM_LOCALE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Company of Heroes\Engine\Locale"
)
STEAM_RELAUNCH_LOCALE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Company of Heroes Relaunch\CoH\Engine\Locale"
)
THQ_LOCALE = Path(r"c:\Program Files (x86)\THQ\Company of Heroes\Engine\Locale")

SEARCH_PATTERNS = ("*French*", "*french*", "RelicCOH.French*.ucs", "RelicCoH.French*.ucs")

CYRILLIC = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")


@dataclass(frozen=True)
class SearchHit:
    path: str
    note: str


def search_local_french() -> list[SearchHit]:
    """Search CE, Steam and THQ installs for any French UCS."""
    hits: list[SearchHit] = []
    roots: list[tuple[Path, str]] = [
        (CE_LOCALE, "Complete Edition CoH\\Engine\\Locale"),
        (STEAM_LOCALE, "Steam CoH Engine\\Locale"),
        (STEAM_RELAUNCH_LOCALE, "Steam CoH Relaunch CoH\\Engine\\Locale"),
        (THQ_LOCALE, "THQ retail Engine\\Locale"),
    ]
    for root, label in roots:
        if not root.is_dir():
            hits.append(SearchHit(str(root), f"{label}: path not found"))
            continue
        french_dirs = [p for p in root.iterdir() if p.is_dir() and "french" in p.name.lower()]
        for d in french_dirs:
            for ucs in d.glob("*.ucs"):
                hits.append(SearchHit(str(ucs), f"{label}: French locale folder"))
        for pattern in SEARCH_PATTERNS:
            for ucs in root.rglob(pattern):
                if ucs.suffix.lower() == ".ucs":
                    hits.append(SearchHit(str(ucs), f"{label}: filename match {pattern}"))
    downloads = Path("downloads")
    if downloads.is_dir():
        for pattern in SEARCH_PATTERNS:
            for ucs in downloads.glob(pattern):
                hits.append(SearchHit(str(ucs), f"downloads/: {pattern}"))
    return hits


def pick_nsv_path(hits: list[SearchHit], explicit: Path | None) -> Path | None:
    """Choose the best official French NSV-like source."""
    if explicit and explicit.is_file():
        return explicit
    candidates: list[Path] = []
    for hit in hits:
        p = Path(hit.path)
        if not p.is_file():
            continue
        name = p.name.lower()
        if "eastern_front" in str(p).lower():
            continue  # mod locale, not base RelicCOH
        if "french" in name and p.suffix.lower() == ".ucs":
            candidates.append(p)
    # Prefer downloads/ NSV naming, then CE/Steam French folder, then THQ.
    def rank(path: Path) -> tuple[int, int]:
        s = str(path).lower()
        if "nsv" in s or "downloads" in s:
            return (0, -path.stat().st_size)
        if "coh\\engine\\locale\\french" in s.replace("/", "\\"):
            return (1, -path.stat().st_size)
        return (2, -path.stat().st_size)

    candidates = sorted(set(candidates), key=rank)
    return candidates[0] if candidates else None


def pick_thq_french(hits: list[SearchHit]) -> Path | None:
    for hit in hits:
        p = Path(hit.path)
        if p.is_file() and "thq" in hit.note.lower() and "french" in p.name.lower():
            return p
    thq = THQ_LOCALE / "French" / "RelicCOH.French.ucs"
    return thq if thq.is_file() else None


def analyze_document(doc: UcsDocument) -> dict:
    return {
        "file": str(doc.path) if doc.path else None,
        "total_keys": len(doc.entries),
        "duplicated_keys": len(doc.duplicates),
        "invalid_lines": len(doc.invalid_lines),
        "missing_placeholder_count": sum(1 for v in doc.entries.values() if v == PLACEHOLDER),
        "cyrillic_value_count": sum(1 for v in doc.entries.values() if CYRILLIC.search(v)),
        "empty_values": sum(1 for v in doc.entries.values() if v == ""),
    }


def _with_entries(base: UcsDocument, entries: dict[int, str]) -> UcsDocument:
    return UcsDocument(
        path=base.path,
        entries=entries,
        encoding=base.encoding,
        has_bom=base.has_bom,
        newline=base.newline,
        trailing_newline=base.trailing_newline,
    )


def build_complete(
    nsv: UcsDocument,
    thq: UcsDocument | None,
    russian: UcsDocument,
    output: Path,
) -> dict:
    """Union NSV French + legacy THQ keys, then fill Russian CE gaps with placeholders."""
    target = nsv
    legacy_only: list[int] = []
    if thq:
        stage1 = merge_documents(nsv, thq, fill_from_source=True)
        target = _with_entries(nsv, stage1.entries)
        legacy_only = sorted(set(thq.entries) - set(nsv.entries))

    result = merge_and_write(target, russian, output, overwrite_output=output.exists())
    return {
        "output": str(output),
        "nsv_keys": len(nsv.entries),
        "thq_keys": len(thq.entries) if thq else 0,
        "legacy_only_from_thq": legacy_only,
        "legacy_only_count": len(legacy_only),
        "russian_gap_placeholders": len(result.added_placeholders),
        "total_keys": len(result.entries),
    }


def write_french_report(
    *,
    search_hits: list[SearchHit],
    nsv_path: Path | None,
    thq_path: Path | None,
    russian_path: Path,
    english_complete_path: Path | None,
    output_path: Path | None,
    build_info: dict | None,
    recovery_notes: list[str],
) -> Path:
    """Write ``report/french/`` with keys, missing ranges, and statistics."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    russian = parse_file(russian_path) if russian_path.is_file() else None
    nsv_doc = parse_file(nsv_path) if nsv_path and nsv_path.is_file() else None
    thq_doc = parse_file(thq_path) if thq_path and thq_path.is_file() else None
    complete_doc = parse_file(output_path) if output_path and output_path.is_file() else None
    english_doc = (
        parse_file(english_complete_path)
        if english_complete_path and english_complete_path.is_file()
        else None
    )

    stats: dict = {
        "recovery": {
            "official_french_found": nsv_doc is not None,
            "nsv_path": str(nsv_path) if nsv_path else None,
            "thq_french_path": str(thq_path) if thq_path else None,
            "output_path": str(output_path) if output_path else None,
            "notes": recovery_notes,
        },
        "search_hits": [{"path": h.path, "note": h.note} for h in search_hits],
    }

    if nsv_doc:
        stats["nsv"] = analyze_document(nsv_doc)
    if thq_doc:
        stats["thq_french"] = analyze_document(thq_doc)
    if complete_doc:
        stats["complete"] = analyze_document(complete_doc)
        val = validate(complete_doc, reference=russian)
        stats["validation"] = {
            "ok": val.ok,
            "errors": len(val.errors),
            "warnings": len(val.warnings),
        }
    if russian:
        stats["russian"] = analyze_document(russian)

    comparisons: dict = {}
    if complete_doc and russian:
        comp_ru = Comparison(russian=russian, english=complete_doc)
        comparisons["vs_russian"] = {
            "missing_in_french": comp_ru.missing_in_english,
            "missing_in_russian": comp_ru.missing_in_russian,
            "coverage_percent": round(
                100.0 * len(comp_ru.common_keys) / len(russian.entries), 4
            ) if russian.entries else 0.0,
        }
        _write_lines(
            REPORT_DIR / "missing_in_french.txt",
            compress_ranges(comp_ru.missing_in_english) or ["(none)"],
        )
        _write_lines(REPORT_DIR / "french_keys.txt", (str(k) for k in complete_doc.keys))

    if complete_doc and english_doc:
        comp_en = Comparison(russian=english_doc, english=complete_doc)
        comparisons["vs_english_complete"] = {
            "missing_in_french": comp_en.missing_in_english,
            "missing_in_english": comp_en.missing_in_russian,
            "coverage_percent": round(
                100.0 * len(comp_en.common_keys) / len(english_doc.entries), 4
            ) if english_doc.entries else 0.0,
        }
        _write_lines(
            REPORT_DIR / "missing_vs_english.txt",
            compress_ranges(comp_en.missing_in_english) or ["(none)"],
        )

    if build_info:
        stats["build"] = build_info
    stats["comparisons"] = comparisons

    if nsv_doc and complete_doc and russian:
        generate_report(Comparison(russian=russian, english=complete_doc), REPORT_DIR)

    (REPORT_DIR / "statistics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    (REPORT_DIR / "search_results.json").write_text(
        json.dumps(
            {
                "local_paths_searched": [
                    str(CE_LOCALE), str(STEAM_LOCALE), str(STEAM_RELAUNCH_LOCALE), str(THQ_LOCALE),
                    "downloads/",
                ],
                "web_search_summary": (
                    "No community-shared RelicCOH.French.ucs download link was found "
                    "(unlike the NSV English Dropbox from the Steam forums thread). "
                    "SteamDB depot 4565 lists CoH/Engine/Locale/French/RelicCoH.French.ucs "
                    "~2.35 MiB in the Legacy Edition French language depot."
                ),
                "depot_downloader": (
                    "DepotDownloader 3.4.0 installed; anonymous login succeeds but "
                    "app 4560 (Legacy Edition) is not licensed on this machine — "
                    "depot 4565 cannot be pulled without a Steam account that owns CoH."
                ),
                "hits": stats["search_hits"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("French report written to %s", REPORT_DIR.resolve())
    return REPORT_DIR


def _write_lines(path: Path, lines) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--russian", type=Path, default=DEFAULT_RUSSIAN)
    ap.add_argument("--english-complete", type=Path, default=DEFAULT_ENGLISH_COMPLETE)
    ap.add_argument("--nsv", type=Path, default=None, help="official French NSV UCS (default: auto-detect)")
    ap.add_argument("--thq", type=Path, default=None, help="THQ retail French UCS (default: auto-detect)")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--search-only", action="store_true")
    ap.add_argument("--report-only", action="store_true", help="rebuild report without writing UCS")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    search_hits = search_local_french()
    recovery_notes: list[str] = []

    official_ucs = [h for h in search_hits if h.path.lower().endswith(".ucs")]
    if official_ucs:
        print("French UCS candidate(s):")
        for h in official_ucs:
            print(f"  {h.path} ({h.note})")
    else:
        print("No French RelicCOH UCS found in local installs or downloads/.")

    nsv_path = pick_nsv_path(search_hits, args.nsv or (DEFAULT_NSV if DEFAULT_NSV.is_file() else None))
    thq_path = args.thq or pick_thq_french(search_hits)

    if nsv_path is None:
        recovery_notes.append(
            "BLOCKER: official French UCS not recovered. Place the file at "
            f"{DEFAULT_NSV} (e.g. from Steam depot 4565 via DepotDownloader if you own "
            "Legacy Edition) and re-run."
        )
        write_french_report(
            search_hits=search_hits,
            nsv_path=None,
            thq_path=thq_path,
            russian_path=args.russian,
            english_complete_path=args.english_complete,
            output_path=args.output if args.output.is_file() else None,
            build_info=None,
            recovery_notes=recovery_notes,
        )
        print("\n".join(recovery_notes))
        return 1

    if args.search_only:
        write_french_report(
            search_hits=search_hits,
            nsv_path=nsv_path,
            thq_path=thq_path,
            russian_path=args.russian,
            english_complete_path=args.english_complete,
            output_path=None,
            build_info={"search_only": True},
            recovery_notes=recovery_notes,
        )
        return 0

    if not args.russian.is_file():
        raise SystemExit(f"Russian reference not found: {args.russian}")

    nsv_doc = parse_file(nsv_path)
    thq_doc = parse_file(thq_path) if thq_path and thq_path.is_file() else None
    russian_doc = parse_file(args.russian)

    build_info = None
    if not args.report_only:
        build_info = build_complete(nsv_doc, thq_doc, russian_doc, args.output)
        print(f"Wrote {args.output} ({build_info['total_keys']} keys)")
        if build_info["russian_gap_placeholders"]:
            print(
                f"WARNING: {build_info['russian_gap_placeholders']} Russian CE id(s) "
                f"filled with {PLACEHOLDER} — official French source is incomplete."
            )

    write_french_report(
        search_hits=search_hits,
        nsv_path=nsv_path,
        thq_path=thq_path,
        russian_path=args.russian,
        english_complete_path=args.english_complete,
        output_path=args.output if args.output.is_file() else None,
        build_info=build_info,
        recovery_notes=recovery_notes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
