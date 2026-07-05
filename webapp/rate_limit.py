"""Per-IP sliding-window rate limiting (in-memory; optional Redis stub)."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque, Optional

# Optional Redis via REDIS_URL — documented but not required for operation.
REDIS_URL = os.environ.get("REDIS_URL", "")

UPLOAD_LIMIT_PER_HOUR = int(os.environ.get("UCS_UPLOAD_LIMIT_PER_HOUR", "30"))
API_LIMIT_PER_MINUTE = int(os.environ.get("UCS_API_LIMIT_PER_MINUTE", "120"))

_hits: dict[str, Deque[float]] = defaultdict(deque)
_upload_hits: dict[str, Deque[float]] = defaultdict(deque)


def _prune(q: Deque[float], window_s: float, now: float) -> None:
    cutoff = now - window_s
    while q and q[0] < cutoff:
        q.popleft()


def check_rate_limit(ip: str, *, upload: bool = False) -> tuple[bool, Optional[str]]:
    """Return (allowed, reason_if_denied)."""
    if REDIS_URL:
        # Stub: Redis backend not wired; fall through to in-memory.
        pass
    now = time.time()
    if upload:
        q = _upload_hits[ip]
        _prune(q, 3600.0, now)
        if len(q) >= UPLOAD_LIMIT_PER_HOUR:
            return False, f"Upload limit ({UPLOAD_LIMIT_PER_HOUR}/hour) exceeded for this IP"
        q.append(now)
        return True, None
    q = _hits[ip]
    _prune(q, 60.0, now)
    if len(q) >= API_LIMIT_PER_MINUTE:
        return False, f"API rate limit ({API_LIMIT_PER_MINUTE}/minute) exceeded"
    q.append(now)
    return True, None
