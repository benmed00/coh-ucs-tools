"""Patch/version chain — consecutive diffs across known CoH UCS editions."""

from __future__ import annotations

from typing import Optional

from parser import UcsDocument
from ucs_analysis import diff_entries

# Ordered localization evolution (THQ retail → NSV → union build).
VERSION_PATCH_CHAIN: list[tuple[str, str]] = [
    ("thq-retail-english", "THQ retail (2006)"),
    ("nsv-english", "New Steam Version"),
    ("complete-english", "Union build (NSV + THQ gaps)"),
]

# Optional CE reference anchor (not a patch step — comparison baseline).
CHAIN_REFERENCE = ("ce-russian", "Complete Edition Russian (reference id set)")


def build_patch_chain(
    documents: dict[str, UcsDocument],
    *,
    chain: list[tuple[str, str]] | None = None,
) -> dict:
    """Compute added/changed counts between consecutive registered versions."""
    steps_def = chain or VERSION_PATCH_CHAIN
    steps: list[dict] = []
    prev_id: Optional[str] = None
    prev_doc: Optional[UcsDocument] = None

    for version_id, label in steps_def:
        doc = documents.get(version_id)
        step: dict = {
            "id": version_id,
            "label": label,
            "available": doc is not None,
            "keys": len(doc.entries) if doc else 0,
            "from_id": prev_id,
            "added": 0,
            "changed": 0,
            "removed": 0,
        }
        if doc and prev_doc:
            missing_rows = diff_entries(prev_doc, doc, "missing")
            step["added"] = sum(1 for r in missing_rows if r.a_value is None and r.b_value is not None)
            step["changed"] = len(diff_entries(prev_doc, doc, "changed"))
            step["removed"] = sum(1 for r in missing_rows if r.a_value is not None and r.b_value is None)
            step["keys_delta"] = len(doc.entries) - len(prev_doc.entries)
        if doc:
            prev_id = version_id
            prev_doc = doc
        steps.append(step)

    ref_id, ref_label = CHAIN_REFERENCE
    ref_doc = documents.get(ref_id)
    return {
        "chain": steps,
        "reference": {
            "id": ref_id,
            "label": ref_label,
            "available": ref_doc is not None,
            "keys": len(ref_doc.entries) if ref_doc else 0,
        },
    }
