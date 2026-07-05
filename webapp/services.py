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
    data = _read_json(GLOSSARY_PATH, {})
    return {str(k): str(v) for k, v in data.items()}


def put_glossary(terms: dict[str, str]) -> dict[str, str]:
    ensure_storage()
    clean = {str(k): str(v) for k, v in terms.items()}
    _write_json(GLOSSARY_PATH, clean)
    return clean


# --------------------------------------------------------------- bookmarks
def get_bookmarks() -> list[int]:
    ensure_storage()
    data = _read_json(BOOKMARKS_PATH, {"ids": []})
    return sorted(int(x) for x in data.get("ids", []))


def add_bookmark(key: int) -> list[int]:
    ids = get_bookmarks()
    if key not in ids:
        ids.append(key)
        ids.sort()
        _write_json(BOOKMARKS_PATH, {"ids": ids})
    return ids


def remove_bookmark(key: int) -> list[int]:
    ids = [i for i in get_bookmarks() if i != key]
    _write_json(BOOKMARKS_PATH, {"ids": ids})
    return ids


def set_bookmarks(ids: list[int]) -> list[int]:
    clean = sorted(set(int(x) for x in ids))
    _write_json(BOOKMARKS_PATH, {"ids": clean})
    return clean


# ------------------------------------------------------------------- audit
MAX_AUDIT = 200


def audit_log(action: str, detail: str = "", *, file_id: str = "") -> None:
    ensure_storage()
    with _lock:
        data = _read_json(AUDIT_PATH, {"entries": []})
        entries = data.get("entries", [])
        entries.append({
            "ts": time.time(),
            "action": action,
            "detail": detail,
            "file_id": file_id,
        })
        data["entries"] = entries[-MAX_AUDIT:]
        _write_json(AUDIT_PATH, data)


def get_audit(limit: int = 50) -> list[dict]:
    ensure_storage()
    entries = _read_json(AUDIT_PATH, {"entries": []}).get("entries", [])
    return list(reversed(entries[-limit:]))


# ---------------------------------------------------------------- MT jobs
_mt_thread: Optional[threading.Thread] = None


def mt_status() -> dict:
    ensure_storage()
    return _read_json(MT_STATUS_PATH, {"status": "idle"})


def mt_report() -> dict:
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
    """Start MT comparison in a background thread (uses translate.py)."""
    global _mt_thread
    ensure_storage()

    def worker() -> None:
        from parser import parse_file
        from translate import MtClient, protect_tokens, restore_tokens

        status = {"status": "running", "progress": 0, "total": 0, "message": "starting"}
        _write_json(MT_STATUS_PATH, status)
        try:
            source = parse_file(source_path)
            ref = parse_file(reference_path) if reference_path and reference_path.exists() else None
            keys = sorted(source.entries.keys())
            if limit:
                keys = keys[:limit]
            status["total"] = len(keys)
            _write_json(MT_STATUS_PATH, status)

            client = MtClient(source=sl, target=tl)
            rows = []
            for idx, key in enumerate(keys, 1):
                ru_val = source.entries[key]
                protected, tokens = protect_tokens(ru_val)
                try:
                    mt_val = restore_tokens(client.translate(protected), tokens)
                except Exception as exc:
                    mt_val = f"[MT error: {exc}]"
                ref_val = ref.entries.get(key, "") if ref else ""
                rows.append({
                    "key": key,
                    "source": ru_val,
                    "mt": mt_val,
                    "reference": ref_val,
                })
                if idx % 10 == 0 or idx == len(keys):
                    _write_json(MT_STATUS_PATH, {
                        "status": "running",
                        "progress": idx,
                        "total": len(keys),
                        "message": f"translated {idx}/{len(keys)}",
                    })
            _write_json(MT_REPORT_PATH, {"rows": rows, "sl": sl, "tl": tl})
            _write_json(MT_STATUS_PATH, {
                "status": "done",
                "progress": len(keys),
                "total": len(keys),
                "message": f"completed {len(keys)} entries",
            })
        except Exception as exc:
            logger.exception("MT job failed")
            _write_json(MT_STATUS_PATH, {
                "status": "error",
                "progress": 0,
                "total": 0,
                "message": str(exc),
            })

    with _lock:
        current = mt_status()
        if current.get("status") == "running" and _mt_thread and _mt_thread.is_alive():
            return {"queued": False, "message": "job already running", **current}
        _mt_thread = threading.Thread(target=worker, daemon=True, name="mt-worker")
        _mt_thread.start()
    return {"queued": True, **mt_status()}


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
    from statistics import Comparison

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
