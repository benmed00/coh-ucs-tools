"""Generate crafted UCS files for duplicate-ID engine testing.

The parser assumes last occurrence wins; this writes a file with intentional
duplicate keys so you can verify in-game which value the Relic engine displays.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from coh_ucs_tools.core.parser import BOM_LE, DEFAULT_NEWLINE

PROBE_KEY = 99999001
PROBE_CONTROL_KEY = 99999002


@dataclass(frozen=True)
class DuplicateProbeSpec:
    key: int = PROBE_KEY
    first_value: str = "DUPLICATE_PROBE_FIRST"
    second_value: str = "DUPLICATE_PROBE_SECOND"
    control_key: int = PROBE_CONTROL_KEY
    control_value: str = "DUPLICATE_PROBE_CONTROL"


def build_duplicate_probe_bytes(spec: DuplicateProbeSpec = DuplicateProbeSpec()) -> bytes:
    """Write raw UTF-16-LE bytes with duplicate lines preserved (not via dict merge)."""
    lines = [
        f"{spec.key}\t{spec.first_value}",
        f"{spec.key}\t{spec.second_value}",
        f"{spec.control_key}\t{spec.control_value}",
    ]
    text = DEFAULT_NEWLINE.join(lines) + DEFAULT_NEWLINE
    return BOM_LE + text.encode("utf-16-le")


def write_duplicate_probe(path: Path | str, *, overwrite: bool = False) -> Path:
    """Write a probe UCS file to *path*."""
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_duplicate_probe_bytes())
    return path


def probe_instructions(path: Path | str) -> list[str]:
    return [
        f"Install {path} as a test locale (back up originals first).",
        f"In-game, search for id {PROBE_KEY} or the probe strings.",
        f"If you see '{DuplicateProbeSpec().second_value}', last-wins is confirmed.",
        f"If you see '{DuplicateProbeSpec().first_value}', first-wins or duplicate rejection.",
        f"Control id {PROBE_CONTROL_KEY} should always show '{DuplicateProbeSpec().control_value}'.",
        "Remove the probe file after testing — never ship it to players.",
    ]
