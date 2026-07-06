"""Synthetic UCS fixtures mimicking CoH1 vs CoH2 key ranges for profile tests."""

from __future__ import annotations

from pathlib import Path

from coh_ucs_tools.core.parser import write_file


def write_coh1_fixture(path: Path) -> Path:
    """CoH1-like: high campaign ids, BOM, CRLF."""
    entries = [
        (559200, "Invasion of Normandy"),
        (9419700, "Causeway"),
        (713520, "MULTIPLAYER"),
        (100, "Panzer"),
    ]
    write_file(path, entries)
    return path


def write_coh2_fixture(path: Path) -> Path:
    """CoH2-like: compact key namespace, no CoH1 campaign ids (500k+)."""
    entries = [(i * 1000, f"coh2-{i}") for i in range(1, 51)]
    write_file(path, entries)
    return path


def write_dow1_fixture(path: Path) -> Path:
    """DoW1-like: BOM-less, moderate key range."""
    entries = [(5000 + i, f"dow-{i}") for i in range(30)]
    write_file(path, entries, add_bom=False)
    return path
