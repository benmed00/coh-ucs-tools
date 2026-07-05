"""File storage for the web service.

All server-side state lives under ``uploads/`` (gitignored):

* ``uploads/files/``      — user-uploaded ``.ucs`` files (UUID-named)
* ``uploads/versions/``   — read-only copies of the built-in known versions
* ``uploads/generated/``  — merge results offered for download
* ``uploads/index.json``  — legacy metadata index (migrated to SQLite on first run)

Metadata is persisted in SQLite (:mod:`webapp.db`); ``.ucs`` bytes stay on disk.
into ``uploads/versions/`` once at startup and served from there.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from parser import UcsDocument, parse_bytes, parse_file

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — the real game files are ~2 MB


@dataclass
class StoredFile:
    """Metadata for one file managed by the store."""

    id: str
    name: str
    kind: str  # "upload" | "version" | "generated"
    stored_path: str
    size: int
    created_at: float
    keys: int = 0
    duplicates: int = 0
    invalid_lines: int = 0
    empty_values: int = 0
    encoding: str = ""
    has_bom: bool = False
    newline: str = ""
    min_key: Optional[int] = None
    max_key: Optional[int] = None
    # version-registry extras
    origin: str = ""
    completeness: str = ""
    notes: str = ""
    project_id: str = ""
    detected_profile: str = ""
    profile_confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class FileStore:
    """Thread-safe registry of uploaded/registered/generated UCS files."""

    def __init__(self, base_dir: Path | str = "uploads") -> None:
        self.base = Path(base_dir)
        self.files_dir = self.base / "files"
        self.versions_dir = self.base / "versions"
        self.generated_dir = self.base / "generated"
        for d in (self.files_dir, self.versions_dir, self.generated_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base / "index.json"
        self._lock = threading.Lock()
        self._records: dict[str, StoredFile] = {}
        self._docs: dict[str, UcsDocument] = {}  # lazy parse cache
        self._db = None
        try:
            from .db import get_db
            self._db = get_db()
            self._load_db()
        except Exception as exc:
            logger.warning("SQLite unavailable, using JSON index: %s", exc)
        if not self._records:
            self._load_index()

    def _load_db(self) -> None:
        if not self._db:
            return
        rows = self._db.fetchall("SELECT * FROM uploads")
        for row in rows:
            rec = StoredFile(
                id=row["id"], name=row["name"], kind=row["kind"],
                stored_path=row["stored_path"], size=row["size"],
                created_at=row["created_at"], keys=row["keys"],
                duplicates=row["duplicates"], invalid_lines=row["invalid_lines"],
                empty_values=row["empty_values"], encoding=row["encoding"],
                has_bom=bool(row["has_bom"]),
                newline=row["newline"] or "",
                min_key=row["min_key"], max_key=row["max_key"],
                origin=row["origin"] or "", completeness=row["completeness"] or "",
                notes=row["notes"] or "", project_id=row["project_id"] or "",
                detected_profile=row["detected_profile"] or "" if "detected_profile" in row.keys() else "",
                profile_confidence=float(row["profile_confidence"] or 0) if "profile_confidence" in row.keys() else 0.0,
            )
            if Path(rec.stored_path).exists():
                self._records[rec.id] = rec
        logger.info("Loaded %d file record(s) from SQLite", len(self._records))

    def _save_db(self, rec: StoredFile) -> None:
        if not self._db:
            return
        self._db.execute(
            """INSERT OR REPLACE INTO uploads
            (id, name, kind, stored_path, size, created_at, keys, duplicates,
             invalid_lines, empty_values, encoding, has_bom, newline,
             min_key, max_key, origin, completeness, notes, project_id,
             detected_profile, profile_confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec.id, rec.name, rec.kind, rec.stored_path, rec.size, rec.created_at,
                rec.keys, rec.duplicates, rec.invalid_lines, rec.empty_values,
                rec.encoding, 1 if rec.has_bom else 0, rec.newline,
                rec.min_key, rec.max_key, rec.origin, rec.completeness,
                rec.notes, rec.project_id, rec.detected_profile, rec.profile_confidence,
            ),
        )

    def _delete_db(self, file_id: str) -> None:
        if self._db:
            self._db.execute("DELETE FROM uploads WHERE id=?", (file_id,))

    # ------------------------------------------------------------- index io
    def _load_index(self) -> None:
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s — starting fresh", self.index_path, exc)
            return
        for raw in data.get("files", []):
            rec = StoredFile(**raw)
            if Path(rec.stored_path).exists():
                self._records[rec.id] = rec
        logger.info("Loaded %d file record(s) from %s", len(self._records), self.index_path)

    def _save_index(self) -> None:
        payload = {"files": [rec.to_dict() for rec in self._records.values()]}
        self.index_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")

    # ---------------------------------------------------------- summarising
    @staticmethod
    def _summarize(rec: StoredFile, doc: UcsDocument) -> None:
        rec.keys = len(doc.entries)
        rec.duplicates = len(doc.duplicates)
        rec.invalid_lines = len(doc.invalid_lines)
        rec.empty_values = sum(1 for v in doc.entries.values() if v == "")
        rec.encoding = doc.encoding
        rec.has_bom = doc.has_bom
        rec.newline = "CRLF" if doc.newline == "\r\n" else "LF"
        if doc.entries:
            rec.min_key = min(doc.entries)
            rec.max_key = max(doc.entries)

    @staticmethod
    def _apply_classification(rec: StoredFile, doc: UcsDocument) -> None:
        from game_profiles import classify_document
        clf = classify_document(doc)
        rec.detected_profile = clf["best_match"]
        rec.profile_confidence = float(clf["confidence"])

    # ------------------------------------------------------------- mutation
    def add_upload(self, filename: str, raw: bytes) -> StoredFile:
        """Store an uploaded file, parse it, and index the summary."""
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError(f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit")
        file_id = uuid.uuid4().hex
        stored = self.files_dir / f"{file_id}.ucs"
        stored.write_bytes(raw)
        doc = parse_bytes(raw, stored)
        rec = StoredFile(
            id=file_id, name=filename or f"{file_id}.ucs", kind="upload",
            stored_path=str(stored), size=len(raw), created_at=time.time(),
        )
        self._summarize(rec, doc)
        self._apply_classification(rec, doc)
        with self._lock:
            self._records[file_id] = rec
            self._docs[file_id] = doc
            self._save_db(rec)
            self._save_index()
        logger.info("Stored upload %s (%s, %d keys)", file_id, rec.name, rec.keys)
        return rec

    def register_version(self, version_id: str, name: str, source: Path, *,
                         origin: str, completeness: str, notes: str) -> Optional[StoredFile]:
        """Copy a known-version file into read-only server storage.

        Skips silently when the source path does not exist so the server
        still starts on machines without the game installed. Never touches
        the source file.
        """
        source = Path(source)
        if not source.exists():
            logger.warning("Version %s not registered — %s does not exist", version_id, source)
            return None
        stored = self.versions_dir / f"{version_id}.ucs"
        with self._lock:
            existing = self._records.get(version_id)
        if not stored.exists() or (existing is None):
            if not stored.exists():
                shutil.copyfile(source, stored)  # read-only copy; source untouched
            doc = parse_file(stored)
            rec = StoredFile(
                id=version_id, name=name, kind="version",
                stored_path=str(stored), size=stored.stat().st_size,
                created_at=time.time(), origin=origin,
                completeness=completeness, notes=notes,
            )
            self._summarize(rec, doc)
            self._apply_classification(rec, doc)
            with self._lock:
                self._records[version_id] = rec
                self._docs[version_id] = doc
                self._save_db(rec)
                self._save_index()
            logger.info("Registered version %s (%d keys)", version_id, rec.keys)
            return rec
        return existing

    def add_generated(self, path: Path, download_name: str) -> StoredFile:
        """Index a merge result stored under ``uploads/generated/``."""
        path = Path(path)
        doc = parse_file(path)
        file_id = path.stem
        rec = StoredFile(
            id=file_id, name=download_name, kind="generated",
            stored_path=str(path), size=path.stat().st_size, created_at=time.time(),
        )
        self._summarize(rec, doc)
        self._apply_classification(rec, doc)
        with self._lock:
            self._records[file_id] = rec
            self._docs[file_id] = doc
            self._save_db(rec)
            self._save_index()
        return rec

    def delete(self, file_id: str) -> bool:
        """Delete an uploaded or generated file. Versions are protected."""
        with self._lock:
            rec = self._records.get(file_id)
            if rec is None:
                return False
            if rec.kind == "version":
                raise PermissionError("Built-in versions are read-only and cannot be deleted")
            self._records.pop(file_id)
            self._docs.pop(file_id, None)
            self._delete_db(file_id)
            self._save_index()
        Path(rec.stored_path).unlink(missing_ok=True)
        logger.info("Deleted %s (%s)", file_id, rec.name)
        return True

    # --------------------------------------------------------------- access
    def get(self, file_id: str) -> Optional[StoredFile]:
        return self._records.get(file_id)

    def list(self, kind: Optional[str] = None) -> list[StoredFile]:
        records = sorted(self._records.values(), key=lambda r: r.created_at)
        if kind:
            records = [r for r in records if r.kind == kind]
        return records

    def document(self, file_id: str) -> UcsDocument:
        """Return the parsed document, loading (and caching) from disk."""
        rec = self._records.get(file_id)
        if rec is None:
            raise KeyError(file_id)
        with self._lock:
            doc = self._docs.get(file_id)
            if doc is None:
                doc = parse_file(rec.stored_path)
                self._docs[file_id] = doc
        return doc
