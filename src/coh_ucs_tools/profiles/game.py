"""Pluggable game-variant profiles for UCS parsing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from coh_ucs_tools.core.parser import UcsDocument, parse_file


@dataclass(frozen=True)
class GameProfile:
    id: str
    name: str
    encoding: str
    newline: str
    separator: str
    notes: str
    bom_required: bool = True
    typical_max_key: int = 11_005_454
    typical_min_key: int = 1


PROFILES: dict[str, GameProfile] = {
    "coh1": GameProfile(
        id="coh1",
        name="Company of Heroes 1",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=True,
        typical_max_key=11_005_454,
        notes="UTF-16-LE with FF FE BOM, CRLF, numeric_id<TAB>text. Engine shows $id No Key for missing ids.",
    ),
    "coh2": GameProfile(
        id="coh2",
        name="Company of Heroes 2",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=True,
        typical_max_key=4_500_000,
        typical_min_key=1,
        notes="Same line format as CoH1; key ranges and campaign namespaces differ. Verify against vscode-relic-ucs.",
    ),
    "dow1": GameProfile(
        id="dow1",
        name="Dawn of War",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=False,
        typical_max_key=2_500_000,
        notes="Dawn of War UCS dialect; id namespaces differ from CoH. BOM may be absent on some builds.",
    ),
    "dow2": GameProfile(
        id="dow2",
        name="Dawn of War II",
        encoding="utf-16-le",
        newline="\r\n",
        separator="\t",
        bom_required=True,
        typical_max_key=3_000_000,
        notes="DoW II UCS — verify against shipped locale files before relying on id heuristics.",
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
            "typical_max_key": p.typical_max_key,
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


def _score_profile(doc: UcsDocument, profile: GameProfile) -> float:
    if not doc.entries:
        return 0.0
    max_k = max(doc.entries)
    min_k = min(doc.entries)
    score = 0.35
    if doc.encoding == profile.encoding:
        score += 0.15
    if doc.newline == profile.newline:
        score += 0.1
    if profile.bom_required and doc.has_bom:
        score += 0.1
    if not profile.bom_required and not doc.has_bom:
        score += 0.05
    if min_k >= profile.typical_min_key:
        score += 0.1
    if max_k <= profile.typical_max_key * 1.05:
        score += 0.15
    elif max_k <= profile.typical_max_key * 1.5:
        score += 0.05
    coh2_cap = PROFILES["coh2"].typical_max_key
    has_coh1_campaign_key = any(k >= 500_000 for k in doc.entries)
    if profile.id == "coh2" and max_k <= coh2_cap * 1.05 and not has_coh1_campaign_key:
        score += 0.03
    if profile.id == "coh1" and (max_k > coh2_cap * 1.15 or has_coh1_campaign_key):
        score += 0.05
    return round(min(score, 1.0), 3)


def classify_document(doc: UcsDocument) -> dict:
    """Heuristic game-variant classification with confidence scores."""
    if not doc.entries:
        return {
            "best_match": "coh1",
            "confidence": 0.0,
            "candidates": [],
            "warnings": ["empty document"],
            "stats": {"keys": 0, "min_key": None, "max_key": None},
        }
    max_k = max(doc.entries)
    min_k = min(doc.entries)
    warnings: list[str] = []
    if not doc.has_bom:
        warnings.append("no BOM — unusual for CoH1/CoH2 retail UCS")
    if doc.newline != "\r\n":
        warnings.append(f"newline is {doc.newline!r}, expected CRLF for Relic UCS")

    ranked = sorted(
        ((pid, _score_profile(doc, p)) for pid, p in PROFILES.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    best_id, best_score = ranked[0]
    return {
        "best_match": best_id,
        "confidence": best_score,
        "candidates": [
            {"id": pid, "name": PROFILES[pid].name, "score": score}
            for pid, score in ranked
        ],
        "warnings": warnings,
        "stats": {"keys": len(doc.entries), "min_key": min_k, "max_key": max_k},
    }


def detect_profile(doc: UcsDocument) -> str:
    """Return the best-matching profile id."""
    return classify_document(doc)["best_match"]


def profile_strict_mismatches(
    items: list[tuple[str, UcsDocument]],
    expected_profile: str,
) -> list[dict]:
    """Return classification mismatches for strict profile checks."""
    out: list[dict] = []
    for file_id, doc in items:
        clf = classify_document(doc)
        if clf["best_match"] != expected_profile:
            out.append({
                "file_id": file_id,
                "best_match": clf["best_match"],
                "confidence": clf["confidence"],
                "expected": expected_profile,
            })
    return out


def validate_against_profile(doc: UcsDocument, profile_id: str = "coh1") -> dict:
    """Check document metadata against a named profile."""
    profile = PROFILES.get(profile_id, PROFILES["coh1"])
    issues: list[dict] = []
    if profile.bom_required and not doc.has_bom:
        issues.append({"code": "bom-missing", "severity": "warning", "message": f"{profile.name} expects BOM"})
    if doc.encoding != profile.encoding:
        issues.append({"code": "encoding", "severity": "warning", "message": f"expected {profile.encoding}, got {doc.encoding}"})
    if doc.newline != profile.newline:
        issues.append({"code": "newline", "severity": "warning", "message": f"expected CRLF, got {doc.newline!r}"})
    if doc.entries:
        max_k = max(doc.entries)
        if max_k > profile.typical_max_key * 1.1:
            issues.append({
                "code": "key-range-high",
                "severity": "info",
                "message": f"max key {max_k} exceeds typical {profile.typical_max_key} for {profile.id}",
            })
    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "ok": not any(i["severity"] == "error" for i in issues),
        "issues": issues,
    }
