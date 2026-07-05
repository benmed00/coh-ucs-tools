"""Interactive CLI for the Company of Heroes UCS toolkit.

Usage::

    python cli.py                       # interactive menu with default paths
    python cli.py --russian R.ucs --english E.ucs
    python merge.py                     # same menu

Menu:

    1 Compare          5 Validate
    2 Statistics       6 Search ID
    3 Export missing   7 Search Text (plain or regex)
    4 Merge            8 Exit
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from merge import PLACEHOLDER, merge_and_write
from parser import UcsDocument, parse_file
from ucs_stats import REPORT_DIR, Comparison, compress_ranges, generate_report
from validator import validate
from verification_checklist import print_checklist_report, run_checklist, run_checklist_file
from duplicate_probe import probe_instructions, write_duplicate_probe
from depot_downloader import download_depot_locale, run_locale_build
from locale_coverage import build_coverage_table, write_coverage_report
from sga_reader import extract_all_locale_ucs, inject_ucs_into_sga, pack_sga, scan_install_locale_archives

logger = logging.getLogger(__name__)

DEFAULT_RUSSIAN = Path(r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale\Russian\RelicCOH.Russian.ucs")
DEFAULT_ENGLISH = Path(r"c:\Program Files (x86)\THQ\Company of Heroes\Engine\Locale\English\RelicCOH.English.ucs")

MENU = """
==== CoH UCS Toolkit ====
1  Compare
2  Statistics
3  Export missing IDs
4  Merge
5  Validate
6  Search ID
7  Search Text
8  Verify checklist (in-game QA)
9  Duplicate probe (engine test file)
10 Exit
"""


@dataclass
class Session:
    russian_path: Path
    english_path: Path
    report_dir: Path
    output: Optional[Path] = None
    _russian: Optional[UcsDocument] = None
    _english: Optional[UcsDocument] = None

    @property
    def russian(self) -> UcsDocument:
        if self._russian is None:
            self._russian = parse_file(self.russian_path)
        return self._russian

    @property
    def english(self) -> UcsDocument:
        if self._english is None:
            self._english = parse_file(self.english_path)
        return self._english

    @property
    def comparison(self) -> Comparison:
        return Comparison(self.russian, self.english)


def cmd_compare(session: Session) -> None:
    comp = session.comparison
    print(f"Russian keys : {len(session.russian.entries)}")
    print(f"English keys : {len(session.english.entries)}")
    print(f"Common keys  : {len(comp.common_keys)}")
    print(f"Missing in English: {len(comp.missing_in_english)}")
    print(f"Missing in Russian: {len(comp.missing_in_russian)}")
    out = generate_report(comp, session.report_dir)
    print(f"Full report written to {out.resolve()}")


def cmd_statistics(session: Session) -> None:
    print(json.dumps(session.comparison.statistics(), indent=2, ensure_ascii=False))


def cmd_export_missing(session: Session) -> None:
    comp = session.comparison
    session.report_dir.mkdir(parents=True, exist_ok=True)
    for name, missing in (("missing_in_english.txt", comp.missing_in_english),
                          ("missing_in_russian.txt", comp.missing_in_russian)):
        path = session.report_dir / name
        path.write_text("\n".join(compress_ranges(missing) or ["(none)"]) + "\n", encoding="utf-8")
        print(f"{path} ({len(missing)} IDs, {len(compress_ranges(missing))} ranges)")


def cmd_merge(session: Session, fill_from_source: bool = False) -> None:
    result = merge_and_write(session.english, session.russian, session.output,
                             fill_from_source=fill_from_source)
    print(f"Preserved {result.preserved} English entries.")
    if fill_from_source:
        print(f"Added {len(result.added_placeholders)} entries copied verbatim "
              f"from the source file (no translations were generated).")
    else:
        print(f"Added {len(result.added_placeholders)} {PLACEHOLDER} placeholders "
              f"(no translations were generated).")
    print(f"Output: {result.output_path.resolve()}")


def cmd_validate(session: Session) -> None:
    for label, doc, ref in (("Russian", session.russian, session.english),
                            ("English", session.english, session.russian)):
        result = validate(doc, reference=ref)
        print(f"--- {label}: {len(result.errors)} error(s), {len(result.warnings)} warning(s) ---")
        shown = 0
        for issue in result.issues:
            if issue.code == "missing-id":
                continue  # summarized below, full list via Export missing IDs
            print(f"  {issue}")
            shown += 1
            if shown >= 50:
                print("  ... (truncated)")
                break
        missing = sum(1 for i in result.issues if i.code == "missing-id")
        if missing:
            print(f"  {missing} ID(s) missing relative to the other language.")


def _print_hits(hits: list[tuple[str, int, str]], limit: int = 50) -> None:
    if not hits:
        print("No matches.")
        return
    for lang, key, value in hits[:limit]:
        text = value if len(value) <= 100 else value[:97] + "..."
        print(f"[{lang}] {key}\t{text}")
    if len(hits) > limit:
        print(f"... {len(hits) - limit} more match(es) not shown.")


def cmd_search_id(session: Session, raw: str) -> None:
    raw = raw.strip()
    if not raw.isdigit():
        print("Please enter a numeric ID.")
        return
    key = int(raw)
    hits = [(lang, key, doc.entries[key])
            for lang, doc in (("RU", session.russian), ("EN", session.english))
            if key in doc.entries]
    _print_hits(hits)


def cmd_verify_checklist(session: Session, which: str = "english") -> None:
    doc = session.english if which == "english" else session.russian
    report = run_checklist(doc)
    report["file"] = str(session.english_path if which == "english" else session.russian_path)
    report["keys"] = len(doc.entries)
    print_checklist_report(report)


def cmd_duplicate_probe(output: Path) -> None:
    path = write_duplicate_probe(output, overwrite=output.exists())
    print(f"Wrote duplicate probe: {path.resolve()}")
    for line in probe_instructions(path):
        print(f"  • {line}")


def cmd_search_text(session: Session, query: str, use_regex: bool) -> None:
    if use_regex:
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as exc:
            print(f"Invalid regex: {exc}")
            return
        match = pattern.search
    else:
        needle = query.lower()
        match = lambda value: needle in value.lower()  # noqa: E731

    hits = [(lang, key, value)
            for lang, doc in (("RU", session.russian), ("EN", session.english))
            for key, value in doc.sorted_entries()
            if match(value)]
    _print_hits(hits)


def interactive(session: Session) -> int:
    while True:
        print(MENU)
        try:
            choice = input("Select> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        try:
            if choice == "1":
                cmd_compare(session)
            elif choice == "2":
                cmd_statistics(session)
            elif choice == "3":
                cmd_export_missing(session)
            elif choice == "4":
                mode = input("Fill missing IDs with (1) <MISSING> placeholders or "
                             "(2) verbatim source text? [1]> ").strip()
                cmd_merge(session, fill_from_source=(mode == "2"))
            elif choice == "5":
                cmd_validate(session)
            elif choice == "6":
                cmd_search_id(session, input("ID> "))
            elif choice == "7":
                query = input("Text (prefix with re: for regex)> ")
                if query.startswith("re:"):
                    cmd_search_text(session, query[3:], use_regex=True)
                else:
                    cmd_search_text(session, query, use_regex=False)
            elif choice == "8":
                which = input("Check English or Russian file? [english]> ").strip().lower()
                cmd_verify_checklist(session, which or "english")
            elif choice == "9":
                out = Path("duplicate-probe.ucs")
                cmd_duplicate_probe(out)
            elif choice == "10":
                return 0
            else:
                print("Unknown choice.")
        except (OSError, ValueError) as exc:
            logger.error("%s", exc)
            print(f"Error: {exc}")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="cli.py",
        description="Compare, validate, search and merge Company of Heroes UCS localization files.")
    ap.add_argument("--russian", type=Path, default=DEFAULT_RUSSIAN, help="path to the Russian .ucs file")
    ap.add_argument("--english", type=Path, default=DEFAULT_ENGLISH, help="path to the English .ucs file")
    ap.add_argument("--report-dir", type=Path, default=REPORT_DIR, help="directory for generated reports")
    ap.add_argument("--output", type=Path, default=None,
                    help="output path for the merged file (default: <english>.merged.ucs in cwd)")
    ap.add_argument("--verbose", "-v", action="store_true", help="enable debug logging")

    sub = ap.add_subparsers(dest="command")
    sub.add_parser("compare", help="compare the files and write the report/ directory")
    sub.add_parser("statistics", help="print statistics JSON")
    sub.add_parser("export-missing", help="export missing ID ranges")
    p = sub.add_parser("merge", help="write the merged UCS file")
    p.add_argument("--fill-from-source", action="store_true",
                   help="fill missing IDs with the source file's original text "
                        "instead of <MISSING> placeholders (verbatim copy, no translation)")
    sub.add_parser("validate", help="run all validations")
    p = sub.add_parser("search-id", help="look an ID up in both files")
    p.add_argument("id")
    p = sub.add_parser("search-text", help="search values by substring or regex")
    p.add_argument("query")
    p.add_argument("--regex", action="store_true", help="treat the query as a regular expression")
    p = sub.add_parser("verify-checklist", help="run in-game QA checklist on a UCS file")
    p.add_argument("file", type=Path, nargs="?", default=None,
                   help="UCS to check (default: --english path)")
    p = sub.add_parser("duplicate-probe", help="write a UCS with duplicate IDs for engine testing")
    p.add_argument("--output", type=Path, default=Path("duplicate-probe.ucs"))
    p = sub.add_parser("depot-download", help="download locale UCS via DepotDownloader (env credentials)")
    p.add_argument("language", nargs="?", default="french", help="french, german, spanish, italian, polish, english")
    p.add_argument("--build", action="store_true", help="run union build after download")
    p = sub.add_parser("coverage-report", help="per-locale coverage table vs Russian CE reference")
    p.add_argument("--reference", type=Path, default=None, help="reference UCS (default: CE Russian)")
    p.add_argument("--json", action="store_true", help="print JSON instead of writing report/")
    p = sub.add_parser("sga-scan", help="scan CoH install for non-stub locale SGA archives")
    p.add_argument("install", type=Path, help="CoH install root directory")
    p = sub.add_parser("sga-extract-locales", help="bulk-extract locale UCS from install SGAs")
    p.add_argument("install", type=Path, help="CoH install root directory")
    p.add_argument("--output", type=Path, default=Path("extracted_locales"))
    p = sub.add_parser("sga-pack", help="pack host files into a new SGA archive")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--compress", action="store_true")
    p.add_argument("mapping", nargs="+", help="internal=host path pairs")
    p = sub.add_parser("sga-inject", help="replace UCS inside an SGA archive")
    p.add_argument("archive", type=Path)
    p.add_argument("internal_path", help="path inside the SGA")
    p.add_argument("ucs_file", type=Path, help="replacement UCS on disk")
    p.add_argument("--output", type=Path, default=None)
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s")

    skip_path_check = args.command in (
        "duplicate-probe", "depot-download", "coverage-report", "sga-scan", "sga-extract-locales",
        "sga-pack", "sga-inject",
    ) or (
        args.command == "verify-checklist" and args.file is not None
    )
    if not skip_path_check:
        for path in (args.russian, args.english):
            if not path.exists():
                print(f"File not found: {path}", file=sys.stderr)
                return 2

    if args.command == "verify-checklist" and args.file is not None:
        if not args.file.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            return 2
        print_checklist_report(run_checklist_file(args.file))
        return 0

    if args.command == "duplicate-probe":
        cmd_duplicate_probe(args.output)
        return 0

    if args.command == "depot-download":
        try:
            result = download_depot_locale(args.language)
        except (ValueError, FileNotFoundError, TimeoutError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        if not result.get("success"):
            print(result.get("error") or result.get("stderr_tail", "Depot download failed"), file=sys.stderr)
            return 1
        print(f"Downloaded {result['dest']} ({result['bytes']} bytes)")
        if args.build:
            build = run_locale_build(args.language)
            print("Build:", "OK" if build.get("built") else build.get("stderr_tail", "failed"))
        return 0

    if args.command == "coverage-report":
        if args.json:
            print(json.dumps(build_coverage_table(reference_path=args.reference), indent=2, ensure_ascii=False))
        else:
            out = write_coverage_report(reference_path=args.reference)
            print(f"Coverage report written to {out.resolve()}")
        return 0

    if args.command == "sga-scan":
        if not args.install.is_dir():
            print(f"Not a directory: {args.install}", file=sys.stderr)
            return 2
        hits = scan_install_locale_archives(args.install)
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        print(f"{len(hits)} archive(s) with locale UCS")
        return 0

    if args.command == "sga-extract-locales":
        if not args.install.is_dir():
            print(f"Not a directory: {args.install}", file=sys.stderr)
            return 2
        results = extract_all_locale_ucs(args.install, args.output)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Extracted {len(results)} file(s) to {args.output.resolve()}")
        return 0

    if args.command == "sga-pack":
        files: dict[str, bytes] = {}
        for pair in args.mapping:
            if "=" not in pair:
                print(f"Invalid mapping (need internal=host): {pair}", file=sys.stderr)
                return 2
            internal, host = pair.split("=", 1)
            host_path = Path(host)
            if not host_path.is_file():
                print(f"File not found: {host_path}", file=sys.stderr)
                return 2
            files[internal] = host_path.read_bytes()
        out = pack_sga(args.output, files, compress=args.compress)
        print(f"Packed {len(files)} file(s) → {out.resolve()} ({out.stat().st_size} bytes)")
        return 0

    if args.command == "sga-inject":
        if not args.archive.is_file():
            print(f"Archive not found: {args.archive}", file=sys.stderr)
            return 2
        if not args.ucs_file.is_file():
            print(f"UCS not found: {args.ucs_file}", file=sys.stderr)
            return 2
        out = args.output or args.archive.with_name(f"{args.archive.stem}-patched.sga")
        inject_ucs_into_sga(args.archive, args.internal_path, args.ucs_file.read_bytes(), out)
        print(f"Wrote {out.resolve()} ({out.stat().st_size} bytes)")
        return 0

    session = Session(args.russian, args.english, args.report_dir, args.output)

    if args.command is None:
        return interactive(session)
    if args.command == "compare":
        cmd_compare(session)
    elif args.command == "statistics":
        cmd_statistics(session)
    elif args.command == "export-missing":
        cmd_export_missing(session)
    elif args.command == "merge":
        cmd_merge(session, fill_from_source=args.fill_from_source)
    elif args.command == "validate":
        cmd_validate(session)
    elif args.command == "search-id":
        cmd_search_id(session, args.id)
    elif args.command == "search-text":
        cmd_search_text(session, args.query, args.regex)
    elif args.command == "verify-checklist":
        cmd_verify_checklist(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
