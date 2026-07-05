"""In-game verification checklist for UCS builds.

After installing ``RelicCOH.English.complete.ucs`` (or another locale build),
run this checklist against the file to confirm known-bad IDs are resolved and
critical menu/campaign strings are present with plausible text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from merge import PLACEHOLDER
from parser import UcsDocument, parse_file

Status = Literal["pass", "fail", "warn", "skip"]


@dataclass(frozen=True)
class CheckItem:
    key: int
    category: str
    label: str
    expected_substrings: tuple[str, ...] = ()
    in_game_hint: str = ""


# Curated from report/verification.md and the original $559200 / $9419700 bug reports.
VERIFICATION_ITEMS: tuple[CheckItem, ...] = (
    CheckItem(
        559200, "tov_campaign", "Invasion of Normandy",
        ("Normandy",),
        "Tales of Valor campaign select — was '$559200 No Key' before fix.",
    ),
    CheckItem(
        9419700, "tov_campaign", "Causeway",
        ("Causeway",),
        "ToV map name — was '$9419700 No Range' before fix.",
    ),
    CheckItem(
        9391740, "tov_campaign", "Falaise Pocket",
        ("Falaise",),
        "ToV / OF campaign map name.",
    ),
    CheckItem(713520, "tov_menu", "MULTIPLAYER menu", ("MULTIPLAYER",), "ToV main menu."),
    CheckItem(713521, "tov_menu", "OPTIONS menu", ("OPTIONS",), "ToV main menu."),
    CheckItem(713530, "tov_menu", "CONTINUE menu", ("CONTINUE",), "ToV main menu."),
    CheckItem(713540, "tov_menu", "SELECT MISSION", ("MISSION",), "ToV operations flow."),
    CheckItem(713544, "tov_menu", "OPERATIONS", ("OPERATIONS",), "ToV operations tab."),
    CheckItem(
        713525, "tov_menu", "Tales of Valor purchase prompt",
        ("Tales of Valor",),
        "Shown when ToV is not owned.",
    ),
    CheckItem(1050, "base_game", "New Army", ("Army",), "Skirmish / army builder."),
    CheckItem(5000, "base_game", "Back button", ("Back",), "Common UI."),
    CheckItem(17000, "base_game", "Delete Profile", ("Delete", "Profile"), "Profile screen."),
    CheckItem(250, "engine", "Font / engine string (low ID)", (), "Low-range engine string — must exist."),
    CheckItem(1, "engine", "Lowest ID (format token)", ("%",), "Engine-internal format token row."),
)


def _check_one(item: CheckItem, doc: UcsDocument) -> dict:
    value = doc.entries.get(item.key)
    if value is None:
        return {
            "key": item.key,
            "category": item.category,
            "label": item.label,
            "status": "fail",
            "value": None,
            "message": "ID missing from file",
            "in_game_hint": item.in_game_hint,
        }
    if value == PLACEHOLDER or value.strip() == PLACEHOLDER:
        return {
            "key": item.key,
            "category": item.category,
            "label": item.label,
            "status": "fail",
            "value": value,
            "message": f"Still {PLACEHOLDER}",
            "in_game_hint": item.in_game_hint,
        }
    if not value.strip():
        return {
            "key": item.key,
            "category": item.category,
            "label": item.label,
            "status": "warn",
            "value": value,
            "message": "Empty value (legal but may show blank in-game)",
            "in_game_hint": item.in_game_hint,
        }
    if item.expected_substrings:
        low = value.lower()
        if not any(s.lower() in low for s in item.expected_substrings):
            return {
                "key": item.key,
                "category": item.category,
                "label": item.label,
                "status": "warn",
                "value": value,
                "message": f"Present but missing expected text ({', '.join(item.expected_substrings)})",
                "in_game_hint": item.in_game_hint,
            }
    return {
        "key": item.key,
        "category": item.category,
        "label": item.label,
        "status": "pass",
        "value": value,
        "message": "OK",
        "in_game_hint": item.in_game_hint,
    }


def run_checklist(doc: UcsDocument) -> dict:
    """Run all verification items against *doc* and return a summary report."""
    rows = [_check_one(item, doc) for item in VERIFICATION_ITEMS]
    passed = sum(1 for r in rows if r["status"] == "pass")
    failed = sum(1 for r in rows if r["status"] == "fail")
    warned = sum(1 for r in rows if r["status"] == "warn")
    return {
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "warned": warned,
        "ok": failed == 0,
        "items": rows,
        "install_tips": [
            "Back up stock RelicCOH.English.ucs before replacing.",
            "Complete Edition: CoH\\Engine\\Locale\\English\\RelicCOH.English.ucs",
            "THQ retail: Engine\\Locale\\English\\RelicCOH.English.ucs",
            "After install, open Tales of Valor → Operations and confirm campaign names render.",
            "If you still see '$id No Key', the wrong file may be loaded or locale.ini points elsewhere.",
        ],
    }


def run_checklist_file(path: Path | str) -> dict:
    doc = parse_file(path)
    report = run_checklist(doc)
    report["file"] = str(path)
    report["keys"] = len(doc.entries)
    return report


def print_checklist_report(report: dict) -> None:
    """Human-readable CLI output."""
    print(f"File: {report.get('file', '(document)')} ({report.get('keys', '?')} keys)")
    print(f"Checklist: {report['passed']} pass, {report['failed']} fail, {report['warned']} warn")
    print()
    for row in report["items"]:
        mark = {"pass": "OK", "fail": "FAIL", "warn": "WARN", "skip": "SKIP"}[row["status"]]
        val = row["value"]
        preview = (val[:60] + "…") if val and len(val) > 60 else (val or "—")
        print(f"  [{mark:4}] {row['key']:>8}  {row['label']}")
        print(f"         {row['message']}  →  {preview!r}")
    print()
    if report["ok"]:
        print("All critical IDs present — safe to verify in-game.")
    else:
        print(f"{report['failed']} item(s) FAILED — do not install until resolved.")
    print()
    print("In-game verification:")
    for tip in report["install_tips"]:
        print(f"  • {tip}")
