"""Build official German ``RelicCOH.German.complete.ucs`` from recovered sources.

CoH1 was officially released in German. Place the recovered NSV German UCS at
``downloads/RelicCOH.German.NSV.ucs`` (Steam depot 4564) and run::

    python build_german.py
    python build_german.py --search-only
    python build_german.py --nsv path/to/German.ucs
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from coh_ucs_tools.config.paths import DOWNLOADS_DIR, REPORTS_DIR
from coh_ucs_tools.locale.build import (
    LocaleConfig,
    build_complete,
    pick_nsv_path,
    pick_thq_locale,
    search_local_locale,
    write_locale_report,
)
from coh_ucs_tools.core.parser import parse_file

DEFAULT_RUSSIAN = Path(
    r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale\Russian\RelicCOH.Russian.ucs"
)
DEFAULT_ENGLISH_COMPLETE = Path("RelicCOH.English.complete.ucs")
DEFAULT_NSV = DOWNLOADS_DIR / "RelicCOH.German.NSV.ucs"
DEFAULT_OUTPUT = Path("RelicCOH.German.complete.ucs")

CONFIG = LocaleConfig(
    language="german",
    language_title="German",
    ucs_basename="RelicCOH.German.ucs",
    search_patterns=(
        "*German*", "*german*", "RelicCOH.German*.ucs", "RelicCoH.German*.ucs",
    ),
    default_nsv=DEFAULT_NSV,
    default_output=DEFAULT_OUTPUT,
    report_dir=REPORTS_DIR / "german",
    depot_app_id=4560,
    depot_id=4564,
    depot_lang="german",
    web_search_note=(
        "CoH Legacy Edition German depot (SteamDB 4564) ships "
        "CoH/Engine/Locale/German/RelicCoH.German.ucs. Pull with DepotDownloader "
        "if you own Legacy Edition."
    ),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--russian", type=Path, default=DEFAULT_RUSSIAN)
    ap.add_argument("--english-complete", type=Path, default=DEFAULT_ENGLISH_COMPLETE)
    ap.add_argument("--nsv", type=Path, default=None)
    ap.add_argument("--thq", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--search-only", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    search_hits = search_local_locale(CONFIG)
    recovery_notes: list[str] = []

    official = [h for h in search_hits if h.path.lower().endswith(".ucs")]
    if official:
        print("German UCS candidate(s):")
        for h in official:
            print(f"  {h.path} ({h.note})")
    else:
        print("No German RelicCOH UCS found in local installs or downloads/.")

    nsv_path = pick_nsv_path(
        search_hits,
        args.nsv or (CONFIG.default_nsv if CONFIG.default_nsv.is_file() else None),
        CONFIG.language,
    )
    thq_path = args.thq or pick_thq_locale(search_hits, CONFIG)

    if nsv_path is None:
        recovery_notes.append(
            f"BLOCKER: official German UCS not recovered. Place at {CONFIG.default_nsv} "
            f"(Steam depot {CONFIG.depot_id} via DepotDownloader) and re-run."
        )
        write_locale_report(
            CONFIG,
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
        write_locale_report(
            CONFIG,
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
        from coh_ucs_tools.core.merge import PLACEHOLDER

        build_info = build_complete(nsv_doc, thq_doc, russian_doc, args.output)
        print(f"Wrote {args.output} ({build_info['total_keys']} keys)")
        if build_info["russian_gap_placeholders"]:
            print(
                f"WARNING: {build_info['russian_gap_placeholders']} Russian CE id(s) "
                f"filled with {PLACEHOLDER}."
            )

    write_locale_report(
        CONFIG,
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
