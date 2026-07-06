"""Merging of UCS documents.

The merge NEVER invents translations. For every ID present in the source
document (Russian) but absent from the target (English), a ``<MISSING>``
placeholder is emitted; existing target values are always preserved
untouched. Output is sorted numerically, encoded exactly like the target
file (UTF-16-LE + BOM, CRLF), and written to a NEW file - originals are
never overwritten.

Running ``python merge.py`` starts the interactive menu from :mod:`coh_ucs_tools.cli`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from coh_ucs_tools.core.parser import UcsDocument, write_file

logger = logging.getLogger(__name__)

PLACEHOLDER = "<MISSING>"
DEFAULT_OUTPUT_SUFFIX = ".merged.ucs"


@dataclass
class MergeResult:
    entries: dict[int, str]
    added_placeholders: list[int] = field(default_factory=list)
    preserved: int = 0
    output_path: Path | None = None


def merge_documents(target: UcsDocument, source: UcsDocument,
                    placeholder: str = PLACEHOLDER,
                    fill_from_source: bool = False) -> MergeResult:
    """Merge ``source`` IDs into ``target``.

    * every entry of ``target`` is kept verbatim;
    * every ID that exists only in ``source`` is added with ``placeholder``
      as its value, or — when ``fill_from_source`` is set — with the
      source file's ORIGINAL text (copied verbatim, never translated);
    * the result is keyed and later written in numeric order.
    """
    merged = dict(target.entries)
    added = []
    for key, source_value in source.entries.items():
        if key not in merged:
            merged[key] = source_value if fill_from_source else placeholder
            added.append(key)
    added.sort()
    logger.info("Merge: kept %d target entries, added %d %s entrie(s)",
                len(target.entries), len(added),
                "source-text" if fill_from_source else "placeholder")
    return MergeResult(entries=merged, added_placeholders=added,
                       preserved=len(target.entries))


def default_output_path(target: UcsDocument) -> Path:
    """``RelicCOH.English.ucs`` -> ``RelicCOH.English.merged.ucs`` (in cwd if
    the original directory is not writable is up to the caller; we default to
    the current working directory to keep game folders pristine)."""
    name = (target.path.name if target.path else "output.ucs")
    if name.lower().endswith(".ucs"):
        name = name[:-4] + DEFAULT_OUTPUT_SUFFIX
    else:
        name += DEFAULT_OUTPUT_SUFFIX
    return Path.cwd() / name


@dataclass
class ThreewayConflict:
    key: int
    base: Optional[str]
    a: Optional[str]
    b: Optional[str]
    resolved: Optional[str] = None


@dataclass
class ThreewayMergeResult:
    entries: dict[int, str]
    conflicts: list[ThreewayConflict]
    output_path: Path | None = None


def merge_threeway(
    base: UcsDocument,
    a: UcsDocument,
    b: UcsDocument,
    *,
    strategy: str = "prefer_a",
) -> ThreewayMergeResult:
    """Three-way merge: base + two branches. strategy: prefer_a|prefer_b|manual_conflicts."""
    all_keys = sorted(base.entries.keys() | a.entries.keys() | b.entries.keys())
    merged: dict[int, str] = {}
    conflicts: list[ThreewayConflict] = []

    for key in all_keys:
        bv = base.entries.get(key)
        av = a.entries.get(key)
        bv2 = b.entries.get(key)
        if av == bv2 or (av is not None and bv2 is not None and av == bv2):
            merged[key] = av if av is not None else bv2  # type: ignore[assignment]
            continue
        if av is not None and bv2 is not None and av != bv2:
            if strategy == "prefer_a":
                merged[key] = av
            elif strategy == "prefer_b":
                merged[key] = bv2
            else:
                conflicts.append(ThreewayConflict(key=key, base=bv, a=av, b=bv2))
                merged[key] = av  # placeholder until manual resolution
            continue
        merged[key] = av if av is not None else bv2  # type: ignore[assignment]

    return ThreewayMergeResult(entries=merged, conflicts=conflicts)


def merge_threeway_and_write(
    base: UcsDocument,
    a: UcsDocument,
    b: UcsDocument,
    output: Path | str,
    *,
    strategy: str = "prefer_a",
    overwrite_output: bool = True,
) -> ThreewayMergeResult:
    result = merge_threeway(base, a, b, strategy=strategy)
    out_path = Path(output)
    write_file(
        out_path,
        sorted(result.entries.items()),
        encoding=a.encoding,
        add_bom=a.has_bom,
        newline=a.newline,
        trailing_newline=a.trailing_newline,
        overwrite=overwrite_output,
    )
    result.output_path = out_path
    return result


def merge_and_write(target: UcsDocument, source: UcsDocument,
                    output: Path | str | None = None,
                    placeholder: str = PLACEHOLDER,
                    overwrite_output: bool = True,
                    fill_from_source: bool = False) -> MergeResult:
    """Merge and write the result to ``output`` (never the original files).

    ``overwrite_output`` only applies to a previously generated merged file;
    writing on top of either input file is always refused.
    """
    result = merge_documents(target, source, placeholder,
                             fill_from_source=fill_from_source)
    out_path = Path(output) if output else default_output_path(target)

    for original in (target.path, source.path):
        if original and out_path.resolve() == Path(original).resolve():
            raise ValueError(f"Refusing to overwrite an original file: {original}")

    write_file(
        out_path,
        sorted(result.entries.items()),
        encoding=target.encoding,
        add_bom=target.has_bom,
        newline=target.newline,
        trailing_newline=target.trailing_newline,
        overwrite=overwrite_output,
    )
    result.output_path = out_path
    return result


if __name__ == "__main__":
    from coh_ucs_tools.cli import main

    raise SystemExit(main())
