"""Relic SGA v2 archive reader — list internal files without full extraction.

Format based on CorsixTH / community modding docs (SGA! magic, version 2).
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SGA_MAGIC = b"SGA!"
STUB_SIZE_THRESHOLD = 10_240


@dataclass(frozen=True)
class SgaFileEntry:
    name: str
    offset: int
    size: int
    folder: str

    @property
    def likely_stub(self) -> bool:
        return self.size < STUB_SIZE_THRESHOLD

    @property
    def full_path(self) -> str:
        if self.folder:
            return f"{self.folder}/{self.name}"
        return self.name


@dataclass(frozen=True)
class SgaArchive:
    path: Path
    version: int
    archive_name: str
    files: list[SgaFileEntry]
    locale_hint: Optional[str] = None
    speech_pack: bool = False


def _read_cstring(data: bytes, offset: int, max_len: int = 256) -> tuple[str, int]:
    end = data.find(b"\x00", offset, offset + max_len)
    if end < 0:
        end = offset + max_len
    name = data[offset:end].decode("ascii", errors="replace")
    return name, end + 1


def read_sga(path: Path | str) -> SgaArchive:
    """Parse SGA v2 header + file table; raise ValueError on unknown format."""
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) < 28:
        raise ValueError(f"File too small for SGA: {path}")

    magic = raw[:4]
    if magic != SGA_MAGIC:
        raise ValueError(f"Not an SGA archive (magic {magic!r}): {path}")

    version = struct.unpack_from("<I", raw, 4)[0]
    if version not in (2, 3):
        raise ValueError(f"Unsupported SGA version {version}: {path}")

    # SGA v2/v3: TOC at end — last uint32 is TOC offset (some builds use uint64).
    toc_offset = struct.unpack_from("<I", raw, len(raw) - 4)[0]
    if toc_offset >= len(raw) or toc_offset < 20:
        # Fallback: scan for folder/file table after fixed header
        toc_offset = 180

    try:
        folder_count = struct.unpack_from("<H", raw, toc_offset)[0]
        file_count = struct.unpack_from("<H", raw, toc_offset + 2)[0]
    except struct.error as exc:
        raise ValueError(f"Cannot read SGA TOC at {toc_offset}: {path}") from exc

    archive_name = path.stem
    folders: list[str] = []
    pos = toc_offset + 4

    for _ in range(folder_count):
        if pos + 4 > len(raw):
            break
        name_off = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        folder_name, _ = _read_cstring(raw, name_off)
        folders.append(folder_name.replace("\\", "/"))

    entries: list[SgaFileEntry] = []
    for _ in range(file_count):
        if pos + 20 > len(raw):
            break
        name_off, folder_idx, data_off, comp_size, decomp_size = struct.unpack_from(
            "<IIIII", raw, pos,
        )
        pos += 20
        fname, _ = _read_cstring(raw, name_off)
        folder = folders[folder_idx] if folder_idx < len(folders) else ""
        size = decomp_size or comp_size
        entries.append(SgaFileEntry(name=fname, offset=data_off, size=size, folder=folder))

    locale_hint = _detect_locale(entries)
    speech = any("speech" in e.full_path.lower() or "sound" in e.full_path.lower()
                 for e in entries)

    return SgaArchive(
        path=path,
        version=version,
        archive_name=archive_name,
        files=sorted(entries, key=lambda e: e.full_path.lower()),
        locale_hint=locale_hint,
        speech_pack=speech,
    )


def _detect_locale(entries: list[SgaFileEntry]) -> Optional[str]:
    for e in entries:
        low = e.full_path.lower()
        for loc in ("english", "french", "german", "russian", "spanish", "italian", "polish", "arabic"):
            if loc in low:
                return loc
    return None


def list_sga_contents(path: Path | str) -> dict:
    """API-friendly listing of SGA internal files."""
    try:
        arch = read_sga(path)
    except (ValueError, OSError) as exc:
        return {"error": str(exc), "files": []}
    return {
        "path": str(arch.path),
        "version": arch.version,
        "archive_name": arch.archive_name,
        "locale_hint": arch.locale_hint,
        "speech_pack": arch.speech_pack,
        "file_count": len(arch.files),
        "files": [
            {
                "path": e.full_path,
                "size": e.size,
                "offset": e.offset,
                "likely_stub": e.likely_stub,
            }
            for e in arch.files
        ],
    }
