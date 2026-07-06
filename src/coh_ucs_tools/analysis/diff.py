"""Extended UCS analysis helpers for diff, lint, fingerprint, subset and search.

Built on :mod:`coh_ucs_tools.core.parser` and :mod:`coh_ucs_tools.core.validator`; stdlib only.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Optional, Sequence

from coh_ucs_tools.config.paths import DOWNLOADS_DIR, PROJECT_ROOT

from coh_ucs_tools.core.parser import UcsDocument, detect_encoding
from coh_ucs_tools.core.text import bad_characters

DiffFilter = Literal["changed", "missing", "empty", "token_mismatch"]

_TOKEN_RE = re.compile(r"%\d[A-Za-z]*%")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_MISSING_LITERAL = "<MISSING>"

# Known NSV English fingerprint (sha256 of repo-local reference when present).
_KNOWN_NSV_SHA256: set[str] = set()


def register_known_nsv_sha256(digest: str) -> None:
    """Register a sha256 hex digest as a known NSV English file."""
    _KNOWN_NSV_SHA256.add(digest.lower())


def _maybe_load_nsv_fingerprint() -> None:
    for base in (DOWNLOADS_DIR, PROJECT_ROOT / "downloads"):
        nsv = base / "RelicCOH.English.NSV.ucs"
        if nsv.exists():
            register_known_nsv_sha256(hashlib.sha256(nsv.read_bytes()).hexdigest())
            return


_maybe_load_nsv_fingerprint()


@dataclass(frozen=True)
class DiffRow:
    """One row in a two-file diff."""

    key: int
    a_value: Optional[str]
    b_value: Optional[str]
    kind: DiffFilter


@dataclass(frozen=True)
class TokenIssue:
    code: str
    message: str
    tokens: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScriptFinding:
    code: str
    detail: str


@dataclass(frozen=True)
class FileFingerprint:
    sha256: str
    size: int
    encoding: str
    has_bom: bool
    bom_hex: str
    crlf_count: int
    lf_only_count: int
    matches_known_nsv: bool


def parse_range_spec(spec: str) -> tuple[int, int]:
    """Parse ``559200`` or ``559200-559650`` into inclusive (start, end)."""
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a.strip()), int(b.strip())
    n = int(spec)
    return n, n


def expand_ranges(ranges: Sequence[str]) -> set[int]:
    """Expand range strings into a set of numeric ids."""
    keys: set[int] = set()
    for spec in ranges:
        start, end = parse_range_spec(spec)
        if end < start:
            start, end = end, start
        keys.update(range(start, end + 1))
    return keys


def subset_by_ranges(entries: dict[int, str], ranges: Sequence[str]) -> dict[int, str]:
    """Return entries whose keys fall within any of ``ranges``."""
    wanted = expand_ranges(ranges)
    return {k: v for k, v in entries.items() if k in wanted}


def apply_patch_overlay(
    base: UcsDocument,
    patch: UcsDocument,
) -> tuple[dict[int, str], list[int], list[int]]:
    """Overlay *patch* entries onto *base*.

    Returns ``(merged_entries, changed_keys, added_keys)``.
    """
    merged = dict(base.entries)
    changed: list[int] = []
    added: list[int] = []
    for key, value in patch.entries.items():
        if key not in merged:
            added.append(key)
            merged[key] = value
        elif merged[key] != value:
            changed.append(key)
            merged[key] = value
    return merged, sorted(changed), sorted(added)


def compare_tokens(a_val: str, b_val: str) -> Optional[TokenIssue]:
    """Return an issue when %token% counts differ between two values."""
    a_tokens = _TOKEN_RE.findall(a_val)
    b_tokens = _TOKEN_RE.findall(b_val)
    if len(a_tokens) != len(b_tokens):
        return TokenIssue(
            code="token-count-mismatch",
            message=f"token count {len(a_tokens)} vs {len(b_tokens)}",
            tokens=[*a_tokens, "---", *b_tokens],
        )
    return None


def token_linter(value: str) -> list[TokenIssue]:
    """Lint UCS format tokens in a single value."""
    issues: list[TokenIssue] = []
    remaining = value
    for tok in _TOKEN_RE.findall(value):
        remaining = remaining.replace(tok, "", 1)
    if remaining.count("%") % 2 != 0:
        issues.append(TokenIssue("unbalanced-percent", "odd number of % characters"))
    if re.search(r"%[^%\s]", remaining):
        issues.append(TokenIssue("unclosed-token", "broken % pattern after removing valid tokens"))
    return issues


def script_detect(value: str) -> list[ScriptFinding]:
    """Detect script / corruption markers in a value."""
    findings: list[ScriptFinding] = []
    if _MISSING_LITERAL in value:
        findings.append(ScriptFinding("missing-literal", "contains <MISSING> placeholder"))
    if _CYRILLIC_RE.search(value):
        findings.append(ScriptFinding("cyrillic", "contains Cyrillic characters"))
    for problem in bad_characters(value):
        if "surrogate" in problem:
            findings.append(ScriptFinding("surrogate", problem))
        else:
            findings.append(ScriptFinding("control-char", problem))
    return findings


def diff_entries(
    a: UcsDocument,
    b: UcsDocument,
    filters: DiffFilter | Sequence[DiffFilter] = "changed",
) -> list[DiffRow]:
    """Compare two documents and return matching diff rows."""
    if isinstance(filters, str):
        filter_set = {filters}
    else:
        filter_set = set(filters)

    all_keys = sorted(a.entries.keys() | b.entries.keys())
    rows: list[DiffRow] = []

    for key in all_keys:
        a_val = a.entries.get(key)
        b_val = b.entries.get(key)
        kinds: set[DiffFilter] = set()

        if a_val is None or b_val is None:
            kinds.add("missing")
        if a_val == "" or b_val == "":
            kinds.add("empty")
        if a_val is not None and b_val is not None and a_val != b_val:
            kinds.add("changed")
        if a_val and b_val and compare_tokens(a_val, b_val):
            kinds.add("token_mismatch")

        matched = kinds & filter_set
        if not matched:
            continue
        kind: DiffFilter = next(iter(matched))
        if "token_mismatch" in matched:
            kind = "token_mismatch"
        elif "missing" in matched:
            kind = "missing"
        elif "empty" in matched:
            kind = "empty"
        elif "changed" in matched:
            kind = "changed"
        rows.append(DiffRow(key=key, a_value=a_val, b_value=b_val, kind=kind))

    return rows


def export_unified_diff(
    a: UcsDocument,
    b: UcsDocument,
    *,
    label_a: str = "a.ucs",
    label_b: str = "b.ucs",
    filters: DiffFilter | Sequence[DiffFilter] = ("changed", "missing"),
) -> str:
    """Return a unified diff of entry lines that differ between two UCS files."""
    if isinstance(filters, str):
        filter_set: Sequence[DiffFilter] = (filters,)
    else:
        filter_set = filters
    rows = diff_entries(a, b, filter_set)
    lines_a = [f"{r.key}\t{r.a_value or ''}" for r in rows]
    lines_b = [f"{r.key}\t{r.b_value or ''}" for r in rows]
    return "".join(
        difflib.unified_diff(
            lines_a, lines_b,
            fromfile=label_a, tofile=label_b,
            lineterm="",
        )
    )


def fingerprint_file(source: Path | bytes) -> FileFingerprint:
    """Compute file fingerprint metadata."""
    if isinstance(source, bytes):
        raw = source
    else:
        raw = Path(source).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    encoding, has_bom = detect_encoding(raw)
    bom_hex = raw[:2].hex(" ").upper() if len(raw) >= 2 else ""
    text = raw.decode(encoding, errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    crlf = text.count("\r\n")
    lf_only = text.count("\n") - crlf
    return FileFingerprint(
        sha256=digest,
        size=len(raw),
        encoding=encoding,
        has_bom=has_bom,
        bom_hex=bom_hex,
        crlf_count=crlf,
        lf_only_count=max(0, lf_only),
        matches_known_nsv=digest.lower() in _KNOWN_NSV_SHA256,
    )


def _normalize_for_fuzzy(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().strip())


def fuzzy_search(
    query: str,
    entries: dict[int, str],
    threshold: float = 0.6,
    limit: int = 50,
) -> list[tuple[int, str, float]]:
    """Fuzzy search entry values using difflib close matches."""
    if not query.strip():
        return []
    nq = _normalize_for_fuzzy(query)
    norm_map: dict[str, list[tuple[int, str]]] = {}
    for key, value in entries.items():
        nv = _normalize_for_fuzzy(value)
        norm_map.setdefault(nv, []).append((key, value))

    candidates = difflib.get_close_matches(nq, list(norm_map.keys()), n=limit * 3, cutoff=threshold)
    results: list[tuple[int, str, float]] = []
    for cand in candidates:
        ratio = difflib.SequenceMatcher(None, nq, cand).ratio()
        for key, value in norm_map[cand]:
            results.append((key, value, round(ratio, 4)))
    results.sort(key=lambda x: (-x[2], x[0]))
    return results[:limit]


def range_heatmap(
    missing_keys: Iterable[int],
    *,
    bucket_size: int = 1000,
) -> list[dict]:
    """Bucket missing keys into heatmap segments."""
    keys = sorted(missing_keys)
    if not keys:
        return []
    min_k, max_k = keys[0], keys[-1]
    start = (min_k // bucket_size) * bucket_size
    end = ((max_k // bucket_size) + 1) * bucket_size
    buckets: list[dict] = []
    key_set = set(keys)
    for bucket_start in range(start, end, bucket_size):
        bucket_end = bucket_start + bucket_size - 1
        count = sum(1 for k in key_set if bucket_start <= k <= bucket_end)
        if count:
            buckets.append({
                "start": bucket_start,
                "end": bucket_end,
                "count": count,
                "missing": True,
            })
    return buckets


def lint_document(doc: UcsDocument) -> dict:
    """Run token + script lint across all entries; return summary + per-key issues."""
    per_key: dict[int, dict] = {}
    token_issues = 0
    script_issues = 0
    for key, value in doc.sorted_entries():
        t_issues = token_linter(value)
        s_findings = script_detect(value)
        if t_issues or s_findings:
            per_key[key] = {
                "token_issues": [{"code": i.code, "message": i.message} for i in t_issues],
                "script_findings": [{"code": f.code, "detail": f.detail} for f in s_findings],
            }
            token_issues += len(t_issues)
            script_issues += len(s_findings)
    return {
        "total_entries": len(doc.entries),
        "entries_with_issues": len(per_key),
        "token_issue_count": token_issues,
        "script_finding_count": script_issues,
        "per_key": per_key,
    }


def crossref_similarity(a_val: str, b_val: str) -> float:
    """Simple similarity ratio between two strings."""
    if not a_val and not b_val:
        return 1.0
    return round(difflib.SequenceMatcher(None, a_val, b_val, autojunk=False).ratio(), 4)


# Campaign ID ranges (approximate, from key distribution in CE Russian UCS).
CAMPAIGN_RANGES: dict[str, list[dict]] = {
    "base": [
        {"name": "Core UI / shared", "start": 1, "end": 50000},
        {"name": "Campaign missions", "start": 50001, "end": 200000},
        {"name": "Units / abilities", "start": 200001, "end": 400000},
    ],
    "opposing_fronts": [
        {"name": "OF campaign", "start": 400001, "end": 550000},
        {"name": "OF units/doctrines", "start": 550001, "end": 700000},
    ],
    "tales_of_valor": [
        {"name": "ToV campaign", "start": 700001, "end": 850000},
        {"name": "ToV units", "start": 850001, "end": 950000},
    ],
    "extended": [
        {"name": "High-range / CE extras", "start": 950001, "end": 11005454},
    ],
}


def campaign_ranges() -> dict[str, list[dict]]:
    return CAMPAIGN_RANGES


def voice_crosslink(ucs_id: int, sga_files: list[dict]) -> list[str]:
    """Heuristic: map UCS id ranges to speech file names from SGA listing."""
    bucket = (ucs_id // 10000) * 10000
    matches = []
    for f in sga_files:
        path = f.get("path", "").lower()
        if "speech" not in path and "sound" not in path and "locale" not in path:
            continue
        if str(bucket)[:3] in path or "english" in path or "russian" in path:
            matches.append(f.get("path", ""))
    return matches[:10]

