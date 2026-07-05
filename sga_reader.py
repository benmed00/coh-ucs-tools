"""Relic SGA v2 archive reader/writer — list, extract, pack, and replace entries.

Format based on CorsixTH / community modding docs (SGA! magic, version 2).
"""

from __future__ import annotations

import logging
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

logger = logging.getLogger(__name__)

SGA_MAGIC = b"SGA!"
HEADER_SIZE = 180
STUB_SIZE_THRESHOLD = 10_240


@dataclass(frozen=True)
class SgaFileEntry:
    name: str
    offset: int
    size: int
    folder: str
    comp_size: int = 0

    @property
    def likely_stub(self) -> bool:
        return self.size < STUB_SIZE_THRESHOLD

    @property
    def compressed(self) -> bool:
        return self.comp_size > 0 and self.comp_size != self.size

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
        entries.append(SgaFileEntry(
            name=fname, offset=data_off, size=size, folder=folder, comp_size=comp_size,
        ))

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


def find_entry(arch: SgaArchive, internal_path: str) -> SgaFileEntry | None:
    """Find a file entry by internal path (case-insensitive)."""
    want = internal_path.replace("\\", "/").lower()
    for e in arch.files:
        if e.full_path.lower() == want or e.name.lower() == want.lower():
            return e
    return None


def extract_entry_bytes(arch: SgaArchive, entry: SgaFileEntry) -> bytes:
    """Read (and decompress if needed) one file from an SGA archive."""
    raw = arch.path.read_bytes()
    read_len = entry.comp_size or entry.size
    if entry.offset + read_len > len(raw):
        raise ValueError(
            f"Entry {entry.full_path!r} extends past archive end "
            f"(offset {entry.offset}, len {read_len}, file {arch.path})"
        )
    data = raw[entry.offset: entry.offset + read_len]
    if entry.compressed:
        try:
            data = zlib.decompress(data)
        except zlib.error as exc:
            raise ValueError(f"zlib decompress failed for {entry.full_path!r}: {exc}") from exc
    if entry.size and len(data) != entry.size:
        logger.warning(
            "Decompressed size %d != expected %d for %s",
            len(data), entry.size, entry.full_path,
        )
    return data


def extract_file(
    archive_path: Path | str,
    internal_path: str,
    output_path: Path | str | None = None,
) -> tuple[bytes, Path | None]:
    """Extract one internal file from an SGA archive to disk (optional)."""
    arch = read_sga(archive_path)
    entry = find_entry(arch, internal_path)
    if entry is None:
        raise ValueError(f"File not found in archive: {internal_path!r}")
    data = extract_entry_bytes(arch, entry)
    out: Path | None = None
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return data, out


def find_locale_ucs(arch: SgaArchive) -> list[SgaFileEntry]:
    """Return UCS entries that look like locale tables."""
    hits: list[SgaFileEntry] = []
    for e in arch.files:
        low = e.full_path.lower()
        if e.name.lower().endswith(".ucs") and (
            "locale" in low or "reliccoh" in low.replace("_", "")
        ):
            hits.append(e)
    return hits


def scan_install_locale_archives(install_root: Path | str) -> list[dict]:
    """Find non-stub SGA archives under an install that contain locale UCS files."""
    root = Path(install_root)
    if not root.is_dir():
        return []
    seen_archives: set[str] = set()
    hits: list[dict] = []
    patterns = (
        "WW2/Archives/**/*.sga",
        "Engine/Archives/**/*.sga",
        "**/Locale/**/*.sga",
        "**/*locale*.sga",
    )
    for pattern in patterns:
        for sga_path in root.glob(pattern):
            if not sga_path.is_file():
                continue
            key = str(sga_path.resolve()).lower()
            if key in seen_archives:
                continue
            seen_archives.add(key)
            if sga_path.stat().st_size < STUB_SIZE_THRESHOLD:
                continue
            try:
                arch = read_sga(sga_path)
            except (ValueError, OSError):
                continue
            locale_entries = [e for e in find_locale_ucs(arch) if not e.likely_stub]
            if not locale_entries:
                continue
            hits.append({
                "archive": str(sga_path),
                "relative": str(sga_path.relative_to(root)) if sga_path.is_relative_to(root) else sga_path.name,
                "locale_hint": arch.locale_hint,
                "locale_ucs": [
                    {"path": e.full_path, "size": e.size}
                    for e in locale_entries
                ],
            })
    return sorted(hits, key=lambda h: h["archive"].lower())


def extract_all_locale_ucs(
    install_root: Path | str,
    output_dir: Path | str,
) -> list[dict]:
    """Extract every locale UCS from non-stub SGAs under *install_root*."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    extracted: list[dict] = []
    for hit in scan_install_locale_archives(install_root):
        arch_path = Path(hit["archive"])
        for entry_info in hit["locale_ucs"]:
            internal = entry_info["path"]
            safe_name = internal.replace("/", "_").replace("\\", "_")
            dest = out / f"{arch_path.stem}__{safe_name}"
            try:
                data, written = extract_file(arch_path, internal, dest)
            except ValueError as exc:
                extracted.append({
                    "archive": str(arch_path),
                    "internal_path": internal,
                    "error": str(exc),
                })
                continue
            extracted.append({
                "archive": str(arch_path),
                "internal_path": internal,
                "output": str(written),
                "bytes": len(data),
            })
    return extracted


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
        "locale_ucs": [e.full_path for e in find_locale_ucs(arch)],
        "files": [
            {
                "path": e.full_path,
                "size": e.size,
                "offset": e.offset,
                "comp_size": e.comp_size,
                "compressed": e.compressed,
                "likely_stub": e.likely_stub,
            }
            for e in arch.files
        ],
    }


def pack_sga(
    output_path: Path | str,
    files: dict[str, bytes],
    *,
    compress: bool = False,
    compress_paths: dict[str, bool] | None = None,
    version: int = 2,
) -> Path:
    """Write a new Relic SGA v2 archive from internal-path → bytes mapping.

    When *compress_paths* is set, each path uses its own zlib flag; otherwise
    the global *compress* boolean applies to every file.
    """
    if not files:
        raise ValueError("No files to pack")
    if version not in (2, 3):
        raise ValueError(f"Unsupported SGA version {version}")

    output_path = Path(output_path)
    items = sorted((p.replace("\\", "/"), data) for p, data in files.items())

    folders: list[str] = []
    folder_index: dict[str, int] = {}
    for path, _ in items:
        folder = PurePosixPath(path).parent.as_posix()
        if folder == ".":
            folder = ""
        if folder not in folder_index:
            folder_index[folder] = len(folders)
            folders.append(folder)

    data_blob = bytearray()
    file_meta: list[tuple[str, int, int, int, int]] = []
    for path, data in items:
        folder = PurePosixPath(path).parent.as_posix()
        if folder == ".":
            folder = ""
        fname = PurePosixPath(path).name
        folder_idx = folder_index[folder]
        do_compress = compress_paths.get(path, compress) if compress_paths is not None else compress
        if do_compress:
            payload = zlib.compress(data)
            comp_size = len(payload)
            decomp_size = len(data)
        else:
            payload = data
            comp_size = decomp_size = len(data)
        data_off = HEADER_SIZE + len(data_blob)
        data_blob.extend(payload)
        file_meta.append((fname, folder_idx, data_off, comp_size, decomp_size))

    strings = bytearray()

    def add_string(text: str) -> int:
        offset = HEADER_SIZE + len(data_blob) + len(strings)
        strings.extend(text.encode("ascii", errors="replace") + b"\x00")
        return offset

    folder_offs = [add_string(f) for f in folders]
    name_offs = [add_string(name) for name, *_ in file_meta]

    toc_start = HEADER_SIZE + len(data_blob) + len(strings)
    toc = bytearray()
    toc.extend(struct.pack("<HH", len(folders), len(file_meta)))
    for fo in folder_offs:
        toc.extend(struct.pack("<I", fo))
    for i, (_, folder_idx, data_off, comp_size, decomp_size) in enumerate(file_meta):
        toc.extend(struct.pack("<IIIII", name_offs[i], folder_idx, data_off, comp_size, decomp_size))

    header = bytearray(HEADER_SIZE)
    header[0:4] = SGA_MAGIC
    struct.pack_into("<I", header, 4, version)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(header) + bytes(data_blob) + bytes(strings) + bytes(toc) + struct.pack("<I", toc_start))
    logger.info("Packed SGA %s (%d files, %d bytes)", output_path, len(file_meta), output_path.stat().st_size)
    return output_path


def repack_sga(
    archive_path: Path | str,
    replacements: dict[str, bytes],
    output_path: Path | str,
    *,
    compress: bool | None = None,
) -> Path:
    """Rebuild an SGA, substituting entries listed in *replacements*."""
    arch = read_sga(archive_path)
    files: dict[str, bytes] = {}
    compress_paths: dict[str, bool] = {}
    for entry in arch.files:
        path = entry.full_path
        if path in replacements:
            files[path] = replacements[path]
        else:
            files[path] = extract_entry_bytes(arch, entry)
        if compress is None:
            compress_paths[path] = entry.compressed
        else:
            compress_paths[path] = bool(compress)
    return pack_sga(
        output_path, files,
        compress=False,
        compress_paths=compress_paths,
        version=arch.version,
    )


def inject_ucs_into_sga(
    archive_path: Path | str,
    internal_path: str,
    ucs_bytes: bytes,
    output_path: Path | str,
) -> Path:
    """Replace one internal UCS file inside an SGA (for mod distribution)."""
    arch = read_sga(archive_path)
    entry = find_entry(arch, internal_path)
    if entry is None:
        raise ValueError(f"File not found in archive: {internal_path!r}")
    want = internal_path.replace("\\", "/")
    for e in arch.files:
        if e.full_path.replace("\\", "/").lower() == want.lower():
            want = e.full_path
            break
    return repack_sga(archive_path, {want: ucs_bytes}, output_path)
