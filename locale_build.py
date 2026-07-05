"""Shared locale union-build pipeline (official NSV + legacy THQ + Russian CE gaps).

Used by ``build_german.py``, ``build_spanish.py``, and similar scripts.
"""

from __future__ import annotations

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

CE_LOCALE = Path(r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale")
STEAM_LOCALE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Company of Heroes\Engine\Locale"
)
STEAM_RELAUNCH_LOCALE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Company of Heroes Relaunch\CoH\Engine\Locale"
)
THQ_LOCALE = Path(r"c:\Program Files (x86)\THQ\Company of Heroes\Engine\Locale")

CYRILLIC = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")


@dataclass(frozen=True)
class LocaleConfig:
    language: str
    language_title: str
    ucs_basename: str
    search_patterns: tuple[str, ...]
    default_nsv: Path
    default_output: Path
    report_dir: Path
    depot_app_id: int
    depot_id: int
    depot_lang: str
    web_search_note: str


@dataclass(frozen=True)
class SearchHit:
    path: str
    note: str


def search_local_locale(cfg: LocaleConfig) -> list[SearchHit]:
    """Search CE, Steam and THQ installs for locale UCS files."""
    hits: list[SearchHit] = []
    lang = cfg.language.lower()
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
        locale_dirs = [p for p in root.iterdir() if p.is_dir() and lang in p.name.lower()]
        for d in locale_dirs:
            for ucs in d.glob("*.ucs"):
                hits.append(SearchHit(str(ucs), f"{label}: {cfg.language_title} locale folder"))
        for pattern in cfg.search_patterns:
            for ucs in root.rglob(pattern):
                if ucs.suffix.lower() == ".ucs":
                    hits.append(SearchHit(str(ucs), f"{label}: filename match {pattern}"))
    downloads = Path("downloads")
    if downloads.is_dir():
        for pattern in cfg.search_patterns:
            for ucs in downloads.glob(pattern):
                hits.append(SearchHit(str(ucs), f"downloads/: {pattern}"))
    return hits


def pick_nsv_path(hits: list[SearchHit], explicit: Path | None, language: str) -> Path | None:
    if explicit and explicit.is_file():
        return explicit
    lang = language.lower()
    candidates: list[Path] = []
    for hit in hits:
        p = Path(hit.path)
        if not p.is_file():
            continue
        if "eastern_front" in str(p).lower():
            continue
        if lang in p.name.lower() and p.suffix.lower() == ".ucs":
            candidates.append(p)

    def rank(path: Path) -> tuple[int, int]:
        s = str(path).lower()
        if "nsv" in s or "downloads" in s:
            return (0, -path.stat().st_size)
        if f"locale\\{lang}" in s.replace("/", "\\"):
            return (1, -path.stat().st_size)
        return (2, -path.stat().st_size)

    candidates = sorted(set(candidates), key=rank)
    return candidates[0] if candidates else None


def pick_thq_locale(hits: list[SearchHit], cfg: LocaleConfig) -> Path | None:
    lang = cfg.language.lower()
    for hit in hits:
        p = Path(hit.path)
        if p.is_file() and "thq" in hit.note.lower() and lang in p.name.lower():
            return p
    thq = THQ_LOCALE / cfg.language_title / cfg.ucs_basename
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


def write_locale_report(
    cfg: LocaleConfig,
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
    cfg.report_dir.mkdir(parents=True, exist_ok=True)
    lang = cfg.language.lower()

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
        "language": cfg.language,
        "recovery": {
            f"official_{lang}_found": nsv_doc is not None,
            "nsv_path": str(nsv_path) if nsv_path else None,
            f"thq_{lang}_path": str(thq_path) if thq_path else None,
            "output_path": str(output_path) if output_path else None,
            "notes": recovery_notes,
        },
        "search_hits": [{"path": h.path, "note": h.note} for h in search_hits],
    }

    if nsv_doc:
        stats["nsv"] = analyze_document(nsv_doc)
    if thq_doc:
        stats[f"thq_{lang}"] = analyze_document(thq_doc)
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
            f"missing_in_{lang}": comp_ru.missing_in_english,
            "missing_in_russian": comp_ru.missing_in_russian,
            "coverage_percent": round(
                100.0 * len(comp_ru.common_keys) / len(russian.entries), 4
            ) if russian.entries else 0.0,
        }
        _write_lines(
            cfg.report_dir / f"missing_in_{lang}.txt",
            compress_ranges(comp_ru.missing_in_english) or ["(none)"],
        )
        _write_lines(
            cfg.report_dir / f"{lang}_keys.txt",
            (str(k) for k in complete_doc.keys),
        )

    if complete_doc and english_doc:
        comp_en = Comparison(russian=english_doc, english=complete_doc)
        comparisons["vs_english_complete"] = {
            f"missing_in_{lang}": comp_en.missing_in_english,
            "missing_in_english": comp_en.missing_in_russian,
            "coverage_percent": round(
                100.0 * len(comp_en.common_keys) / len(english_doc.entries), 4
            ) if english_doc.entries else 0.0,
        }

    if build_info:
        stats["build"] = build_info
    stats["comparisons"] = comparisons

    if nsv_doc and complete_doc and russian:
        generate_report(Comparison(russian=russian, english=complete_doc), cfg.report_dir)

    (cfg.report_dir / "statistics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (cfg.report_dir / "search_results.json").write_text(
        json.dumps(
            {
                "language": cfg.language,
                "local_paths_searched": [
                    str(CE_LOCALE), str(STEAM_LOCALE), str(STEAM_RELAUNCH_LOCALE), str(THQ_LOCALE),
                    "downloads/",
                ],
                "web_search_summary": cfg.web_search_note,
                "depot": {
                    "app_id": cfg.depot_app_id,
                    "depot_id": cfg.depot_id,
                    "lang": cfg.depot_lang,
                    "command": (
                        f"DepotDownloader -app {cfg.depot_app_id} -depot {cfg.depot_id} "
                        f"-lang {cfg.depot_lang}"
                    ),
                },
                "hits": stats["search_hits"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("%s report written to %s", cfg.language_title, cfg.report_dir.resolve())
    return cfg.report_dir


def _write_lines(path: Path, lines) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
