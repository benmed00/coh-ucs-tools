"""Pluggable game-variant profiles for UCS parsing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from parser import UcsDocument, parse_file


@dataclass(frozen=True)
class GameProfile:
    id: str
    name: str
    encoding: str
    newline: str
    separator: str
    notes: str
    bom_required: bool = True


PROFILES: dict[str, GameProfile] = {
    "coh1": GameProfile(
        id="coh1",
        name="Company of Heroes 1",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=True,
        notes="UTF-16-LE with FF FE BOM, CRLF, numeric_id<TAB>text. Engine shows $id No Key for missing ids.",
    ),
    "coh2": GameProfile(
        id="coh2",
        name="Company of Heroes 2",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=True,
        notes="Same line format as CoH1; key ranges and campaign namespaces differ. Verify against vscode-relic-ucs.",
    ),
    "dow1": GameProfile(
        id="dow1",
        name="Dawn of War",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=False,
        notes="Dawn of War UCS dialect; id namespaces differ from CoH. BOM may be absent on some builds.",
    ),
}


def list_profiles() -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "encoding": p.encoding,
            "newline": "CRLF" if p.newline == "\r\n" else "LF",
            "separator": "tab",
            "bom_required": p.bom_required,
            "notes": p.notes,
        }
        for p in PROFILES.values()
    ]


def parse_with_profile(path: Path | str, profile_id: str = "coh1") -> UcsDocument:
    """Parse a UCS file using the selected game profile (encoding hints)."""
    profile = PROFILES.get(profile_id, PROFILES["coh1"])
    doc = parse_file(path)
    if profile.bom_required and not doc.has_bom:
        doc.notes = f"Warning: {profile.name} expects a BOM"  # type: ignore[attr-defined]
    return doc


def detect_profile(doc: UcsDocument) -> str:
    """Heuristic profile detection from document metadata."""
    if doc.encoding.startswith("utf-16"):
        return "coh1"
    return "coh1"
