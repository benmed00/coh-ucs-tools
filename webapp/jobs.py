"""MT job queue with SQLite persistence and glossary injection."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .db import get_db

logger = logging.getLogger(__name__)

JOB_STATES = frozenset({"queued", "running", "paused", "done", "failed", "cancelled"})


@dataclass
class MtJob:
    id: str
    status: str
    sl: str
    tl: str
    source_path: str
    reference_path: Optional[str] = None
    progress: int = 0
    total: int = 0
    retry_count: int = 0
    message: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def progress_percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(100.0 * self.progress / self.total, 1)


_workers: dict[str, threading.Thread] = {}
_cancel_flags: dict[str, threading.Event] = {}
_pause_flags: dict[str, threading.Event] = {}
_lock = threading.Lock()


def _save_job(job: MtJob) -> None:
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO mt_jobs
        (id, status, sl, tl, source_path, reference_path, progress, total,
         retry_count, message, created_at, updated_at, report_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job.id, job.status, job.sl, job.tl, job.source_path, job.reference_path,
            job.progress, job.total, job.retry_count, job.message,
            job.created_at, job.updated_at, json.dumps(job.report),
        ),
    )


def _load_job(job_id: str) -> Optional[MtJob]:
    row = get_db().fetchone("SELECT * FROM mt_jobs WHERE id=?", (job_id,))
    if not row:
        return None
    return MtJob(
        id=row["id"], status=row["status"], sl=row["sl"], tl=row["tl"],
        source_path=row["source_path"], reference_path=row["reference_path"],
        progress=row["progress"], total=row["total"], retry_count=row["retry_count"],
        message=row["message"], created_at=row["created_at"], updated_at=row["updated_at"],
        report=json.loads(row["report_json"] or "{}"),
    )


def get_glossary_from_db() -> dict[str, str]:
    rows = get_db().fetchall("SELECT term, replacement FROM glossary")
    return {r["term"]: r["replacement"] for r in rows}


def _translate_backend(client, text: str) -> str:
    """DeepL if DEEPL_API_KEY set, else Google gtx."""
    deepl_key = os.environ.get("DEEPL_API_KEY", "")
    if deepl_key:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({
            "auth_key": deepl_key,
            "text": text,
            "source_lang": client.source.upper(),
            "target_lang": client.target.upper(),
        }).encode()
        req = urllib.request.Request(
            "https://api-free.deepl.com/v2/translate",
            data=data, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["translations"][0]["text"]
    return client.translate(text)


def _run_job(job_id: str, limit: Optional[int]) -> None:
    from parser import parse_file
    from translate import MtClient, protect_tokens, restore_tokens, compare

    cancel = _cancel_flags.setdefault(job_id, threading.Event())
    pause = _pause_flags.setdefault(job_id, threading.Event())
    job = _load_job(job_id)
    if not job:
        return

    try:
        job.status = "running"
        job.message = "loading source"
        job.updated_at = time.time()
        _save_job(job)

        source = parse_file(job.source_path)
        ref = parse_file(job.reference_path) if job.reference_path and Path(job.reference_path).exists() else None
        keys = sorted(source.entries.keys())
        if limit:
            keys = keys[:limit]
        job.total = len(keys)
        _save_job(job)

        glossary = get_glossary_from_db()
        client = MtClient(source=job.sl, target=job.tl)
        rows = []
        cache: dict[str, str] = {}

        for idx, key in enumerate(keys, 1):
            if cancel.is_set():
                job.status = "cancelled"
                job.message = f"cancelled at {idx}/{len(keys)}"
                break
            while pause.is_set() and not cancel.is_set():
                job.status = "paused"
                job.message = f"paused at {idx}/{len(keys)}"
                job.updated_at = time.time()
                _save_job(job)
                time.sleep(0.5)

            val = source.entries[key]
            protected, tokens = protect_tokens(val)
            for term, repl in glossary.items():
                protected = protected.replace(term, repl)
            try:
                mt_val = restore_tokens(_translate_backend(client, protected), tokens)
            except Exception as exc:
                job.retry_count += 1
                mt_val = f"[MT error: {exc}]"
            ref_val = ref.entries.get(key, "") if ref else ""
            cache[str(key)] = mt_val
            rows.append({"key": key, "source": val, "mt": mt_val, "reference": ref_val})

            job.progress = idx
            job.status = "running"
            job.message = f"translated {idx}/{len(keys)}"
            job.updated_at = time.time()
            if idx % 5 == 0 or idx == len(keys):
                job.report = {"rows": rows, "sl": job.sl, "tl": job.tl}
                _save_job(job)

        if job.status not in ("cancelled", "failed"):
            if ref:
                comp_rows = compare(cache, source.entries, ref.entries, keys, glossary=glossary)
                job.report = {
                    "rows": rows, "sl": job.sl, "tl": job.tl,
                    "comparison": [{"key": r.key, "similarity": r.similarity} for r in comp_rows[:500]],
                }
            else:
                job.report = {"rows": rows, "sl": job.sl, "tl": job.tl}
            job.status = "done"
            job.message = f"completed {len(rows)} entries"
    except Exception as exc:
        logger.exception("MT job %s failed", job_id)
        job.status = "failed"
        job.message = str(exc)
    job.updated_at = time.time()
    _save_job(job)


def queue_job(
    *,
    source_path: Path,
    reference_path: Optional[Path],
    sl: str,
    tl: str,
    limit: Optional[int] = None,
) -> MtJob:
    with _lock:
        for jid, thread in list(_workers.items()):
            j = _load_job(jid)
            if j and j.status == "running" and thread.is_alive():
                raise RuntimeError(f"Job {jid} already running")

        job = MtJob(
            id=uuid.uuid4().hex,
            status="queued",
            sl=sl, tl=tl,
            source_path=str(source_path),
            reference_path=str(reference_path) if reference_path else None,
            message="queued",
        )
        _save_job(job)
        _cancel_flags[job.id] = threading.Event()
        _pause_flags[job.id] = threading.Event()
        thread = threading.Thread(target=_run_job, args=(job.id, limit), daemon=True, name=f"mt-{job.id[:8]}")
        _workers[job.id] = thread
        thread.start()
    return job


def cancel_job(job_id: str) -> Optional[MtJob]:
    ev = _cancel_flags.get(job_id)
    if ev:
        ev.set()
    job = _load_job(job_id)
    if job and job.status in ("queued", "running", "paused"):
        job.status = "cancelled"
        job.updated_at = time.time()
        _save_job(job)
    return job


def pause_job(job_id: str) -> Optional[MtJob]:
    ev = _pause_flags.get(job_id)
    if ev:
        ev.set()
    return _load_job(job_id)


def resume_job(job_id: str) -> Optional[MtJob]:
    ev = _pause_flags.get(job_id)
    if ev:
        ev.clear()
    job = _load_job(job_id)
    if job and job.status == "paused":
        job.status = "running"
        job.updated_at = time.time()
        _save_job(job)
    return job


def latest_job() -> Optional[MtJob]:
    row = get_db().fetchone("SELECT id FROM mt_jobs ORDER BY updated_at DESC LIMIT 1")
    return _load_job(row["id"]) if row else None


def job_status_dict(job: Optional[MtJob] = None) -> dict:
    job = job or latest_job()
    if not job:
        return {"status": "idle", "progress": 0, "total": 0, "message": "", "progress_percent": 0}
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "total": job.total,
        "message": job.message,
        "retry_count": job.retry_count,
        "progress_percent": job.progress_percent,
    }
