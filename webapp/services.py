"""Webapp runtime services: JSON storage, audit log, MT jobs, batch compare."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(__file__).parent / "storage"
GLOSSARY_PATH = STORAGE_DIR / "glossary.json"
BOOKMARKS_PATH = STORAGE_DIR / "bookmarks.json"
AUDIT_PATH = STORAGE_DIR / "audit.json"
MT_STATUS_PATH = STORAGE_DIR / "mt_status.json"
MT_REPORT_PATH = STORAGE_DIR / "mt_report.json"
BATCH_DIR = STORAGE_DIR / "batch_jobs"

_lock = threading.Lock()


def ensure_storage() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    for path, default in (
        (GLOSSARY_PATH, {}),
        (BOOKMARKS_PATH, {"ids": []}),
        (AUDIT_PATH, {"entries": []}),
        (MT_STATUS_PATH, {"status": "idle", "progress": 0, "total": 0, "message": ""}),
        (MT_REPORT_PATH, {"rows": []}),
    ):
        if not path.exists():
            path.write_text(json.dumps(default, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- glossary
def get_glossary() -> dict[str, str]:
    ensure_storage()
    try:
        from .db import get_db
        rows = get_db().fetchall("SELECT term, replacement FROM glossary")
        if rows:
            return {r["term"]: r["replacement"] for r in rows}
    except Exception:
        pass
    data = _read_json(GLOSSARY_PATH, {})
    return {str(k): str(v) for k, v in data.items()}


def put_glossary(terms: dict[str, str]) -> dict[str, str]:
    ensure_storage()
    clean = {str(k): str(v) for k, v in terms.items()}
    _write_json(GLOSSARY_PATH, clean)
    try:
        from .db import get_db
        import time as _time
        db = get_db()
        db.execute("DELETE FROM glossary")
        now = _time.time()
        for term, repl in clean.items():
            db.execute(
                "INSERT INTO glossary(term, replacement, updated_at) VALUES (?,?,?)",
                (term, repl, now),
            )
    except Exception:
        pass
    return clean


# --------------------------------------------------------------- bookmarks
def get_bookmarks() -> list[int]:
    ensure_storage()
    try:
        from .db import get_db
        rows = get_db().fetchall("SELECT key_id FROM bookmarks ORDER BY key_id")
        if rows:
            return [int(r["key_id"]) for r in rows]
    except Exception:
        pass
    data = _read_json(BOOKMARKS_PATH, {"ids": []})
    return sorted(int(x) for x in data.get("ids", []))


def add_bookmark(key: int) -> list[int]:
    ids = get_bookmarks()
    if key not in ids:
        ids.append(key)
        ids.sort()
        _write_json(BOOKMARKS_PATH, {"ids": ids})
        try:
            from .db import get_db
            get_db().execute(
                "INSERT OR IGNORE INTO bookmarks(key_id, created_at) VALUES (?,?)",
                (key, time.time()),
            )
        except Exception:
            pass
    return ids


def remove_bookmark(key: int) -> list[int]:
    ids = [i for i in get_bookmarks() if i != key]
    _write_json(BOOKMARKS_PATH, {"ids": ids})
    try:
        from .db import get_db
        get_db().execute("DELETE FROM bookmarks WHERE key_id=?", (key,))
    except Exception:
        pass
    return ids


def set_bookmarks(ids: list[int]) -> list[int]:
    clean = sorted(set(int(x) for x in ids))
    _write_json(BOOKMARKS_PATH, {"ids": clean})
    return clean


# ------------------------------------------------------------------- audit
MAX_AUDIT = 200


def audit_log(action: str, detail: str = "", *, file_id: str = "") -> None:
    ensure_storage()
    entry = {"ts": time.time(), "action": action, "detail": detail, "file_id": file_id}
    with _lock:
        data = _read_json(AUDIT_PATH, {"entries": []})
        entries = data.get("entries", [])
        entries.append(entry)
        data["entries"] = entries[-MAX_AUDIT:]
        _write_json(AUDIT_PATH, data)
    try:
        from .db import get_db
        get_db().execute(
            "INSERT INTO audit_log(ts, action, detail, file_id) VALUES (?,?,?,?)",
            (entry["ts"], action, detail, file_id),
        )
    except Exception:
        pass


def get_audit(limit: int = 50) -> list[dict]:
    ensure_storage()
    try:
        from .db import get_db
        rows = get_db().fetchall(
            "SELECT ts, action, detail, file_id FROM audit_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        if rows:
            return [dict(r) for r in rows]
    except Exception:
        pass
    entries = _read_json(AUDIT_PATH, {"entries": []}).get("entries", [])
    return list(reversed(entries[-limit:]))


# ---------------------------------------------------------------- MT jobs
def mt_status() -> dict:
    from . import jobs
    return jobs.job_status_dict()


def mt_report() -> dict:
    from . import jobs
    job = jobs.latest_job()
    if job and job.report:
        return job.report
    ensure_storage()
    return _read_json(MT_REPORT_PATH, {"rows": []})


def queue_mt_job(
    *,
    source_path: Path,
    reference_path: Optional[Path],
    sl: str,
    tl: str,
    limit: Optional[int],
) -> dict:
    """Start MT comparison via the persistent job queue."""
    from . import jobs

    try:
        job = jobs.queue_job(
            source_path=source_path, reference_path=reference_path,
            sl=sl, tl=tl, limit=limit,
        )
        return {"queued": True, **jobs.job_status_dict(job)}
    except RuntimeError as exc:
        return {"queued": False, "message": str(exc), **jobs.job_status_dict()}


# ----------------------------------------------------------- batch compare
@dataclass
class BatchJob:
    id: str
    file_ids: list[str]
    created_at: float
    status: str = "done"
    pairs: list[dict] = field(default_factory=list)


def run_batch_compare(file_ids: list[str], store) -> BatchJob:
    """Compare all pairs; write JSON zip to batch dir."""
    from ucs_stats import Comparison

    job_id = uuid.uuid4().hex
    pairs = []
    for i, a in enumerate(file_ids):
        for b in file_ids[i + 1:]:
            comp = Comparison(russian=store.document(a), english=store.document(b))
            pairs.append({
                "a": a,
                "b": b,
                "statistics": comp.statistics(),
            })
    job = BatchJob(id=job_id, file_ids=file_ids, created_at=time.time(), pairs=pairs)
    ensure_storage()
    job_path = BATCH_DIR / f"{job_id}.json"
    _write_json(job_path, asdict(job))
    zip_path = BATCH_DIR / f"{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.json", json.dumps(asdict(job), indent=2))
    audit_log("batch_compare", f"{len(file_ids)} files, {len(pairs)} pairs", file_id=job_id)
    return job


def batch_zip_path(job_id: str) -> Optional[Path]:
    p = BATCH_DIR / f"{job_id}.zip"
    return p if p.exists() else None


def fire_webhooks(event: str, payload: dict) -> None:
    """Fire registered webhooks (metadata only, no string content)."""
    try:
        import urllib.request
        from .db import get_db
        rows = get_db().fetchall("SELECT url, events FROM webhooks")
        for row in rows:
            events = json.loads(row["events"] or "[]")
            if event not in events:
                continue
            body = json.dumps({"event": event, **payload}).encode()
            req = urllib.request.Request(
                row["url"], data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except Exception as exc:
                logger.warning("Webhook %s failed: %s", row["url"], exc)
    except Exception:
        pass


def cleanup_old_uploads(store, max_age_hours: float = 24) -> int:
    """Delete uploads and generated files older than max_age_hours."""
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for rec in list(store.list()):
        if rec.kind == "version":
            continue
        if rec.created_at < cutoff:
            try:
                store.delete(rec.id)
                removed += 1
            except (PermissionError, KeyError):
                pass
    if removed:
        audit_log("cleanup", f"removed {removed} stale file(s)")
    return removed
