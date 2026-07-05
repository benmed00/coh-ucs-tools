"""SQLite persistence for webapp state (stdlib sqlite3 only)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(os.environ.get("SQLITE_PATH", "webapp/data/app.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at REAL NOT NULL,
    keys INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    invalid_lines INTEGER DEFAULT 0,
    empty_values INTEGER DEFAULT 0,
    encoding TEXT DEFAULT '',
    has_bom INTEGER DEFAULT 0,
    newline TEXT DEFAULT '',
    min_key INTEGER,
    max_key INTEGER,
    origin TEXT DEFAULT '',
    completeness TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    project_id TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bookmarks (
    key_id INTEGER PRIMARY KEY,
    project_id TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary (
    term TEXT PRIMARY KEY,
    replacement TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS mt_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    sl TEXT NOT NULL,
    tl TEXT NOT NULL,
    source_path TEXT NOT NULL,
    reference_path TEXT,
    progress INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    message TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    report_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    file_id TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS community_hashes (
    sha256 TEXT PRIMARY KEY,
    key_count INTEGER NOT NULL,
    label TEXT NOT NULL,
    registered_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    events TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_label TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_uploads_kind ON uploads(kind);
CREATE INDEX IF NOT EXISTS idx_uploads_project ON uploads(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_mt_jobs_status ON mt_jobs(status);
"""


class Database:
    """Thread-safe SQLite wrapper."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate_json_storage()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.cursor() as cur:
            cur.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _migrate_json_storage(self) -> None:
        """One-time migration from webapp/storage/*.json into SQLite."""
        storage = Path(__file__).parent / "storage"
        if not storage.exists():
            return

        glossary_path = storage / "glossary.json"
        if glossary_path.exists():
            try:
                data = json.loads(glossary_path.read_text(encoding="utf-8"))
                existing = self.fetchone("SELECT COUNT(*) AS c FROM glossary")
                if existing and existing["c"] == 0 and data:
                    now = time.time()
                    with self.cursor() as cur:
                        for term, repl in data.items():
                            cur.execute(
                                "INSERT OR IGNORE INTO glossary(term, replacement, updated_at) VALUES (?,?,?)",
                                (str(term), str(repl), now),
                            )
                    logger.info("Migrated %d glossary term(s) from JSON", len(data))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Glossary migration skipped: %s", exc)

        bookmarks_path = storage / "bookmarks.json"
        if bookmarks_path.exists():
            try:
                data = json.loads(bookmarks_path.read_text(encoding="utf-8"))
                existing = self.fetchone("SELECT COUNT(*) AS c FROM bookmarks")
                if existing and existing["c"] == 0:
                    ids = data.get("ids", [])
                    now = time.time()
                    with self.cursor() as cur:
                        for kid in ids:
                            cur.execute(
                                "INSERT OR IGNORE INTO bookmarks(key_id, created_at) VALUES (?,?)",
                                (int(kid), now),
                            )
                    logger.info("Migrated %d bookmark(s) from JSON", len(ids))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Bookmarks migration skipped: %s", exc)

        audit_path = storage / "audit.json"
        if audit_path.exists():
            try:
                data = json.loads(audit_path.read_text(encoding="utf-8"))
                existing = self.fetchone("SELECT COUNT(*) AS c FROM audit_log")
                if existing and existing["c"] == 0:
                    entries = data.get("entries", [])
                    with self.cursor() as cur:
                        for e in entries:
                            cur.execute(
                                "INSERT INTO audit_log(ts, action, detail, file_id) VALUES (?,?,?,?)",
                                (e.get("ts", time.time()), e.get("action", ""),
                                 e.get("detail", ""), e.get("file_id", "")),
                            )
                    logger.info("Migrated %d audit entry(ies) from JSON", len(entries))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Audit migration skipped: %s", exc)

        index_path = Path("uploads/index.json")
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                existing = self.fetchone("SELECT COUNT(*) AS c FROM uploads")
                if existing and existing["c"] == 0:
                    files = data.get("files", [])
                    with self.cursor() as cur:
                        for raw in files:
                            cur.execute(
                                """INSERT OR IGNORE INTO uploads
                                (id, name, kind, stored_path, size, created_at, keys, duplicates,
                                 invalid_lines, empty_values, encoding, has_bom, newline,
                                 min_key, max_key, origin, completeness, notes)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    raw["id"], raw["name"], raw["kind"], raw["stored_path"],
                                    raw["size"], raw["created_at"], raw.get("keys", 0),
                                    raw.get("duplicates", 0), raw.get("invalid_lines", 0),
                                    raw.get("empty_values", 0), raw.get("encoding", ""),
                                    1 if raw.get("has_bom") else 0, raw.get("newline", ""),
                                    raw.get("min_key"), raw.get("max_key"),
                                    raw.get("origin", ""), raw.get("completeness", ""),
                                    raw.get("notes", ""),
                                ),
                            )
                    logger.info("Migrated %d upload record(s) from index.json", len(files))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Upload index migration skipped: %s", exc)

    def close(self) -> None:
        self._conn.close()


_db: Optional[Database] = None
_db_lock = threading.Lock()


def get_db(path: Path | str | None = None) -> Database:
    global _db
    with _db_lock:
        if _db is None:
            _db = Database(path or DEFAULT_DB_PATH)
        return _db
