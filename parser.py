"""UCS (Relic localization) file parser and writer.

Reverse-engineered format (verified against RelicCOH.Russian.ucs and
RelicCOH.English.ucs):

* Encoding:      UTF-16 little-endian.
* BOM:           2 bytes ``FF FE`` at the start of the file.
* Line endings:  CRLF (``\\r\\n``). No lone LF/CR occur in the originals.
* Entry syntax:  ``<numeric id><TAB><text>``. The value is everything after
  the FIRST tab; values may legally contain further tabs.
* Comments:      the format has no comment syntax. Any line that does not
  match the entry syntax is recorded as invalid instead of silently dropped.
* Duplicates:    not present in the shipped files. When they occur, the LAST
  occurrence wins (matching typical "later overrides earlier" engine
  behaviour); every occurrence is recorded for reporting.
* Empty values:  legal (``<id><TAB>`` followed by end of line).

Only the standard library is required. ``chardet`` is used opportunistically
as a fallback when a file has no BOM and is not valid UTF-16.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

BOM_LE = b"\xff\xfe"
BOM_BE = b"\xfe\xff"
DEFAULT_ENCODING = "utf-16-le"
DEFAULT_NEWLINE = "\r\n"

_KEY_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class UcsEntry:
    """A single valid ``id<TAB>value`` line."""

    key: int
    value: str
    line_number: int  # 1-based line number in the source file


@dataclass(frozen=True)
class InvalidLine:
    """A line that could not be parsed as a UCS entry."""

    line_number: int
    raw: str
    reason: str


@dataclass
class UcsDocument:
    """In-memory representation of a UCS file.

    ``entries`` is the ``Dictionary<int, string>`` view (duplicates collapsed,
    last occurrence wins). ``all_entries`` preserves every valid line in file
    order for diagnostics.
    """

    path: Optional[Path] = None
    entries: dict[int, str] = field(default_factory=dict)
    all_entries: list[UcsEntry] = field(default_factory=list)
    duplicates: dict[int, list[int]] = field(default_factory=dict)
    invalid_lines: list[InvalidLine] = field(default_factory=list)
    encoding: str = DEFAULT_ENCODING
    has_bom: bool = True
    newline: str = DEFAULT_NEWLINE
    trailing_newline: bool = True
    empty_line_count: int = 0

    @property
    def keys(self) -> list[int]:
        """All unique keys, sorted numerically."""
        return sorted(self.entries)

    def sorted_entries(self) -> list[tuple[int, str]]:
        """(key, value) pairs sorted numerically by key."""
        return sorted(self.entries.items())


def detect_encoding(raw: bytes) -> tuple[str, bool]:
    """Return ``(encoding, has_bom)`` for a UCS byte string.

    BOM detection covers the two UTF-16 byte orders. Without a BOM we try
    strict UTF-16-LE, then optionally chardet, then fall back to UTF-8.
    """
    if raw.startswith(BOM_LE):
        return "utf-16-le", True
    if raw.startswith(BOM_BE):
        return "utf-16-be", True
    try:
        raw.decode("utf-16-le")
        return "utf-16-le", False
    except UnicodeDecodeError:
        pass
    try:  # optional dependency
        import chardet

        guess = chardet.detect(raw)
        if guess.get("encoding"):
            logger.debug("chardet guessed %s (%.0f%%)", guess["encoding"], 100 * guess.get("confidence", 0))
            return guess["encoding"], False
    except ImportError:
        logger.debug("chardet not installed; falling back to utf-8")
    return "utf-8", False


def parse_text(text: str, path: Optional[Path] = None) -> UcsDocument:
    """Parse already-decoded UCS text (no BOM) into a :class:`UcsDocument`."""
    doc = UcsDocument(path=path)
    doc.trailing_newline = text.endswith(("\n", "\r"))
    if "\r\n" in text:
        doc.newline = "\r\n"
    elif "\n" in text:
        doc.newline = "\n"

    occurrences: dict[int, list[int]] = {}
    lines = text.split(doc.newline) if doc.newline in text else [text]
    # A trailing newline produces one final empty pseudo-line: not a real line.
    if lines and lines[-1] == "" and doc.trailing_newline:
        lines.pop()

    for line_number, line in enumerate(lines, 1):
        if line == "":
            doc.empty_line_count += 1
            continue
        if "\t" not in line:
            doc.invalid_lines.append(InvalidLine(line_number, line, "no tab separator"))
            continue
        key_part, value = line.split("\t", 1)
        if not _KEY_RE.fullmatch(key_part):
            doc.invalid_lines.append(InvalidLine(line_number, line, f"non-numeric key {key_part!r}"))
            continue
        key = int(key_part)
        entry = UcsEntry(key, value, line_number)
        doc.all_entries.append(entry)
        occurrences.setdefault(key, []).append(line_number)
        doc.entries[key] = value  # last occurrence wins

    doc.duplicates = {k: lines_ for k, lines_ in occurrences.items() if len(lines_) > 1}
    if doc.duplicates:
        logger.warning("%s: %d duplicate key(s)", path or "<memory>", len(doc.duplicates))
    if doc.invalid_lines:
        logger.warning("%s: %d invalid line(s)", path or "<memory>", len(doc.invalid_lines))
    return doc


def parse_bytes(raw: bytes, path: Optional[Path] = None) -> UcsDocument:
    """Parse raw UCS bytes, auto-detecting encoding and BOM."""
    encoding, has_bom = detect_encoding(raw)
    text = raw.decode(encoding)
    if text.startswith("\ufeff"):
        text = text[1:]
    doc = parse_text(text, path)
    doc.encoding = encoding
    doc.has_bom = has_bom
    return doc


def parse_file(path: Path | str) -> UcsDocument:
    """Parse a UCS file from disk."""
    path = Path(path)
    logger.info("Parsing %s", path)
    doc = parse_bytes(path.read_bytes(), path)
    logger.info(
        "%s: %d keys, %d duplicates, %d invalid lines",
        path.name, len(doc.entries), len(doc.duplicates), len(doc.invalid_lines),
    )
    return doc


def serialize(entries: Iterable[tuple[int, str]], *, newline: str = DEFAULT_NEWLINE,
              trailing_newline: bool = True) -> str:
    """Serialize (key, value) pairs to UCS text (without BOM)."""
    body = newline.join(f"{key}\t{value}" for key, value in entries)
    if body and trailing_newline:
        body += newline
    return body


def write_file(path: Path | str, entries: Iterable[tuple[int, str]], *,
               encoding: str = DEFAULT_ENCODING, add_bom: bool = True,
               newline: str = DEFAULT_NEWLINE, trailing_newline: bool = True,
               overwrite: bool = False) -> Path:
    """Write entries to a UCS file, preserving the on-disk conventions.

    Refuses to overwrite an existing file unless ``overwrite=True`` so the
    original game files can never be clobbered by accident.
    """
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    text = serialize(entries, newline=newline, trailing_newline=trailing_newline)
    raw = text.encode(encoding)
    if add_bom and encoding.startswith("utf-16"):
        raw = (BOM_LE if encoding == "utf-16-le" else BOM_BE) + raw
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    logger.info("Wrote %s (%d bytes)", path, len(raw))
    return path
