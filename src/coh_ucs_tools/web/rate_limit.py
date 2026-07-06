"""Per-IP sliding-window rate limiting (in-memory or optional Redis)."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Deque, Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "")

UPLOAD_LIMIT_PER_HOUR = int(os.environ.get("UCS_UPLOAD_LIMIT_PER_HOUR", "30"))
API_LIMIT_PER_MINUTE = int(os.environ.get("UCS_API_LIMIT_PER_MINUTE", "120"))

_hits: dict[str, Deque[float]] = defaultdict(deque)
_upload_hits: dict[str, Deque[float]] = defaultdict(deque)
_redis_client = None
_redis_checked = False


def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    if not REDIS_URL:
        return None
    try:
        import redis

        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("Rate limiting backed by Redis at %s", REDIS_URL.split("@")[-1])
    except Exception as exc:
        logger.warning("REDIS_URL set but Redis unavailable (%s); using in-memory limits", exc)
        _redis_client = None
    return _redis_client


def _prune(q: Deque[float], window_s: float, now: float) -> None:
    cutoff = now - window_s
    while q and q[0] < cutoff:
        q.popleft()


def _redis_check(ip: str, *, upload: bool) -> Optional[tuple[bool, Optional[str]]]:
    client = _get_redis()
    if client is None:
        return None
    window = 3600 if upload else 60
    limit = UPLOAD_LIMIT_PER_HOUR if upload else API_LIMIT_PER_MINUTE
    key = f"ucs:{'upload' if upload else 'api'}:{ip}"
    now = int(time.time())
    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window + 10)
        _, count, _, _ = pipe.execute()
        if count >= limit:
            label = f"{limit}/hour" if upload else f"{limit}/minute"
            return False, f"Rate limit ({label}) exceeded for this IP"
        return True, None
    except Exception as exc:
        logger.warning("Redis rate limit error: %s", exc)
        return None


def check_rate_limit(ip: str, *, upload: bool = False) -> tuple[bool, Optional[str]]:
    """Return (allowed, reason_if_denied)."""
    if os.environ.get("UCS_WEBAPP_UPLOADS"):
        return True, None
    redis_result = _redis_check(ip, upload=upload)
    if redis_result is not None:
        return redis_result

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
