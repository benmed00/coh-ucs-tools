"""Build unofficial Arabic machine-translated UCS from English complete.

CoH1 was never officially released in Arabic. This script searches for any
community Arabic UCS (expected: none), then machine-translates
``RelicCOH.English.complete.ucs`` (en→ar) with token preservation, writing
``RelicCOH.Arabic.MT.ucs`` — clearly labeled fan MT, not official Relic text.

Usage::

    python build_arabic.py --search-only     # document search results only
    python build_arabic.py --limit 200       # pilot MT run
    python build_arabic.py                   # full build (resumes from cache)
    python build_arabic.py --report-only     # rebuild report from cache + UCS
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from parser import parse_file, write_file
from ucs_stats import Comparison, generate_report
from translate import MtClient, protect_tokens, restore_tokens, translate_text
from validator import validate

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = Path("RelicCOH.English.complete.ucs")
DEFAULT_OUTPUT = Path("RelicCOH.Arabic.MT.ucs")
CACHE_PATH = Path("downloads/mt_ar_cache.json")
REPORT_DIR = Path("report/arabic")

CE_LOCALE = Path(r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale")
STEAM_LOCALE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Company of Heroes\Engine\Locale"
)
THQ_LOCALE = Path(r"c:\Program Files (x86)\THQ\Company of Heroes\Engine\Locale")

SEARCH_PATTERNS = ("*Arabic*", "*arabic*", "RelicCOH.Arabic*.ucs")

SAMPLE_IDS = (250, 559200, 9419700)
TOKEN_SAMPLE_IDS = (1, 1018, 1022)
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_TOKEN_RE = re.compile(r"%\d[A-Za-z]*%")


@dataclass(frozen=True)
class SearchHit:
    path: str
    note: str


def search_local_arabic() -> list[SearchHit]:
    """Search CE install and common mod paths for any Arabic UCS."""
    hits: list[SearchHit] = []
    roots: list[tuple[Path, str]] = [
        (CE_LOCALE, "Complete Edition Engine\\Locale"),
        (STEAM_LOCALE, "Steam CoH Engine\\Locale"),
        (THQ_LOCALE, "THQ retail Engine\\Locale"),
    ]
    for root, label in roots:
        if not root.is_dir():
            hits.append(SearchHit(str(root), f"{label}: path not found"))
            continue
        arabic_dirs = [p for p in root.iterdir() if p.is_dir() and "arabic" in p.name.lower()]
        for d in arabic_dirs:
            for ucs in d.glob("*.ucs"):
                hits.append(SearchHit(str(ucs), f"{label}: Arabic locale folder"))
        for pattern in SEARCH_PATTERNS:
            for ucs in root.rglob(pattern):
                if ucs.suffix.lower() == ".ucs":
                    hits.append(SearchHit(str(ucs), f"{label}: filename match {pattern}"))
    return hits


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def translate_entries(
    english: dict[int, str],
    *,
    workers: int = 4,
    checkpoint_every: int = 200,
    limit: int | None = None,
    delay_s: float = 0.12,
) -> dict[str, str]:
    """Translate all English values to Arabic, resuming from ``CACHE_PATH``."""
    cache = load_cache()
    keys = sorted(english.keys())
    if limit is not None:
        keys = keys[:limit]

    def needs_mt(key: int) -> bool:
        return str(key) not in cache and english.get(key, "").strip() != ""

    todo = [k for k in keys if needs_mt(k)]
    logger.info(
        "Arabic MT: %d target(s), %d cached, %d to fetch",
        len(keys), len(keys) - len(todo), len(todo),
    )
    if not todo:
        return cache

    client = MtClient(source="en", target="ar", delay_s=delay_s)
    done = 0
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(translate_text, english[k], client): k for k in todo
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                cache[str(key)] = future.result()
            except RuntimeError as exc:
                logger.error("id %d: %s", key, exc)
                cache[str(key)] = english[key]  # fallback: keep English on failure
            done += 1
            if done % checkpoint_every == 0:
                save_cache(cache)
                elapsed = time.monotonic() - started
                rate = done / elapsed if elapsed else 0.0
                eta_s = (len(todo) - done) / rate if rate else 0.0
                logger.info("MT progress: %d/%d (ETA ~%.0fs)", done, len(todo), eta_s)
                print(f"progress {done}/{len(todo)}", flush=True)
    save_cache(cache)
    return cache


def build_arabic_entries(english: dict[int, str], cache: dict[str, str]) -> dict[int, str]:
    """Assemble Arabic entries: MT from cache, empty strings preserved."""
    arabic: dict[int, str] = {}
    for key, value in english.items():
        if not value.strip():
            arabic[key] = value
        else:
            arabic[key] = cache.get(str(key), value)
    return arabic


def check_token_preservation(english: dict[int, str], arabic: dict[int, str]) -> dict:
    """Verify every English format token appears unchanged in the Arabic value."""
    checked = 0
    mismatches: list[dict] = []
    for key, en_val in english.items():
        tokens = _TOKEN_RE.findall(en_val)
        if not tokens:
            continue
        checked += 1
        ar_val = arabic.get(key, "")
        for tok in tokens:
            if tok not in ar_val:
                mismatches.append({"id": key, "token": tok, "english": en_val, "arabic": ar_val})
                break
    return {"entries_with_tokens": checked, "mismatches": mismatches[:20], "mismatch_count": len(mismatches)}


def validate_arabic_ucs(path: Path, english_doc_path: Path) -> dict:
    """Run validator and custom checks on the output UCS."""
    doc = parse_file(path)
    english = parse_file(english_doc_path)
    result = validate(doc, reference=english)

    roundtrip = parse_file(path)
    roundtrip_ok = roundtrip.entries == doc.entries

    arabic_lines = sum(1 for v in doc.entries.values() if _ARABIC_RE.search(v))
    sample_checks = {}
    for key in (*SAMPLE_IDS, *TOKEN_SAMPLE_IDS):
        en = english.entries.get(key, "")
        ar = doc.entries.get(key, "")
        sample_checks[str(key)] = {
            "english": en,
            "arabic": ar,
            "has_arabic_script": bool(_ARABIC_RE.search(ar)) if ar.strip() else None,
            "tokens_preserved": all(t in ar for t in _TOKEN_RE.findall(en)),
        }

    return {
        "path": str(path),
        "key_count": len(doc.entries),
        "validation_ok": result.ok,
        "errors": len(result.errors),
        "warnings": len(result.warnings),
        "utf16_roundtrip_ok": roundtrip_ok,
        "lines_with_arabic_script": arabic_lines,
        "sample_ids": sample_checks,
        "token_preservation": check_token_preservation(english.entries, doc.entries),
    }


def write_arabic_report(
    english_path: Path,
    arabic_path: Path,
    cache: dict[str, str],
    search_hits: list[SearchHit],
    validation: dict,
    *,
    sample_size: int = 50,
) -> Path:
    """Write ``report/arabic/`` statistics and sample comparison TSV."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    english = parse_file(english_path)
    arabic = parse_file(arabic_path) if arabic_path.exists() else None

    mt_keys = [k for k, v in english.entries.items() if v.strip()]
    cached_mt = sum(1 for k in mt_keys if str(k) in cache and cache[str(k)].strip())
    coverage = round(100.0 * cached_mt / len(mt_keys), 2) if mt_keys else 100.0

    if arabic:
        generate_report(Comparison(russian=english, english=arabic), REPORT_DIR)
    comparison_stats: dict = {}
    comp_path = REPORT_DIR / "statistics.json"
    if comp_path.exists():
        comparison_stats = json.loads(comp_path.read_text(encoding="utf-8"))

    stats = {
        **comparison_stats,
        "source": "machine_translation",
        "official_arabic_found": any("Arabic locale" in h.note or "filename match" in h.note for h in search_hits),
        "source_file": str(english_path),
        "output_file": str(arabic_path),
        "english_key_count": len(english.entries),
        "arabic_key_count": len(arabic.entries) if arabic else 0,
        "mt_cache_entries": len(cache),
        "mt_coverage_percent": coverage,
        "validation": validation,
        "search_hits": [{"path": h.path, "note": h.note} for h in search_hits],
        "disclaimer": (
            "Unofficial fan machine translation (en→ar via Google Translate public endpoint). "
            "NOT official Relic/THQ text. CoH1 engine may not render RTL Arabic correctly."
        ),
    }
    (REPORT_DIR / "statistics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    rng = random.Random(42)
    pool = [k for k in english.entries if english.entries[k].strip()]
    sample_keys = sorted(rng.sample(pool, min(sample_size, len(pool))))

    tsv_path = REPORT_DIR / "sample_comparison.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("id\tenglish\tarabic_mt\n")
        for key in sample_keys:
            en = english.entries[key].replace("\t", " ").replace("\r", " ").replace("\n", " ")
            ar = (arabic.entries.get(key, cache.get(str(key), "")) if arabic else cache.get(str(key), ""))
            ar = ar.replace("\t", " ").replace("\r", " ").replace("\n", " ")
            fh.write(f"{key}\t{en}\t{ar}\n")

    (REPORT_DIR / "search_results.json").write_text(
        json.dumps(
            {
                "local_paths_searched": [str(CE_LOCALE), str(STEAM_LOCALE), str(THQ_LOCALE)],
                "web_search_summary": (
                    "No community RelicCOH.Arabic.ucs or CoH1 Arabic localization patch found. "
                    "Web results reference the 2013 film subtitles or general mod-translation guides, "
                    "not a shipped/fan Arabic UCS for CoH1."
                ),
                "hits": stats["search_hits"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("Arabic report written to %s", REPORT_DIR.resolve())
    return REPORT_DIR


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help="English complete UCS (MT input)")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                    help="Arabic MT output UCS")
    ap.add_argument("--limit", type=int, default=None, help="translate only the first N keys")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--search-only", action="store_true", help="only run the Arabic UCS search")
    ap.add_argument("--report-only", action="store_true",
                    help="skip MT; rebuild report from cache and existing output")
    ap.add_argument("--skip-write", action="store_true",
                    help="run MT but do not write the output UCS")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    search_hits = search_local_arabic()
    official = [h for h in search_hits if h.path.lower().endswith(".ucs")]
    if official:
        print("Found potential Arabic UCS file(s):")
        for h in official:
            print(f"  {h.path} ({h.note})")
    else:
        print("No Arabic UCS found locally (expected). Will use machine translation.")

    if args.search_only:
        write_arabic_report(
            args.source, args.output, load_cache(), search_hits,
            validation={"search_only": True},
        )
        return 0

    if not args.source.is_file():
        raise SystemExit(f"Source not found: {args.source}")

    english_doc = parse_file(args.source)
    print(f"English source keys: {len(english_doc.entries)}")

    cache = load_cache() if args.report_only else translate_entries(
        english_doc.entries,
        workers=args.workers,
        limit=args.limit,
    )

    if not args.skip_write and not args.report_only:
        arabic_entries = build_arabic_entries(english_doc.entries, cache)
        write_file(
            args.output,
            sorted(arabic_entries.items()),
            overwrite=args.output.exists(),
        )
        print(f"Wrote {args.output} ({len(arabic_entries)} keys)")

    validation = {}
    if args.output.is_file():
        validation = validate_arabic_ucs(args.output, args.source)
        print(json.dumps({k: validation[k] for k in (
            "key_count", "validation_ok", "lines_with_arabic_script",
            "sample_ids", "token_preservation",
        )}, indent=2, ensure_ascii=False))

    write_arabic_report(args.source, args.output, cache, search_hits, validation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
