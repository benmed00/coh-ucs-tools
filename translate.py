"""Automated machine translation and comparison against reference text.

Machine-translates Russian UCS values (Google Translate's public ``gtx``
endpoint, no API key) and compares the result with a reference English UCS
file (e.g. the recovered official New Steam Version localization).

The MT output is NEVER written into a game file - it is used purely for
cross-checking the recovered official translations. Results are checkpointed
to ``downloads/mt_cache.json`` so interrupted runs resume where they left
off.

Usage::

    python translate.py --limit 400          # translate a sample
    python translate.py                      # translate everything missing
    python translate.py --compare-only       # just rebuild the report
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from parser import parse_file

logger = logging.getLogger(__name__)

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
CACHE_PATH = Path("downloads/mt_cache.json")
REPORT_TSV = Path("report/translation_comparison.tsv")
REPORT_JSON = Path("report/translation_summary.json")

DEFAULT_RUSSIAN = Path(r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale\Russian\RelicCOH.Russian.ucs")
DEFAULT_OLD_ENGLISH = Path(r"c:\Program Files (x86)\THQ\Company of Heroes\Engine\Locale\English\RelicCOH.English.ucs")
DEFAULT_REFERENCE = Path("downloads/RelicCOH.English.NSV.ucs")

_TOKEN_RE = re.compile(r"%\d[A-Za-z]*%")  # UCS format tokens like %1% / %1NAME%


@dataclass(frozen=True)
class ComparisonRow:
    key: int
    russian: str
    machine: str
    official: str
    similarity: float


class MtClient:
    """Tiny thread-safe client for the public translate endpoint."""

    def __init__(self, source: str = "ru", target: str = "en",
                 delay_s: float = 0.1, max_retries: int = 4) -> None:
        self.source, self.target = source, target
        self.delay_s, self.max_retries = delay_s, max_retries
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last_request + self.delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def translate(self, text: str) -> str:
        query = urllib.parse.urlencode({
            "client": "gtx", "sl": self.source, "tl": self.target,
            "dt": "t", "q": text,
        })
        url = f"{ENDPOINT}?{query}"
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.load(resp)
                return "".join(seg[0] for seg in data[0] if seg and seg[0])
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                backoff = 2.0 * (attempt + 1)
                logger.warning("MT request failed (%s); retry in %.0fs", exc, backoff)
                time.sleep(backoff)
        raise RuntimeError(f"Translation failed after {self.max_retries} retries")


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def translate_missing(russian: dict[int, str], targets: list[int],
                      workers: int = 4, checkpoint_every: int = 200) -> dict[str, str]:
    """Translate ``targets`` (IDs) from the Russian dict, resuming from cache."""
    cache = load_cache()
    todo = [k for k in targets if str(k) not in cache and russian.get(k, "").strip()]
    logger.info("MT: %d target(s), %d cached, %d to fetch", len(targets), len(targets) - len(todo), len(todo))
    if not todo:
        return cache

    client = MtClient()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(client.translate, russian[k]): k for k in todo}
        for future in as_completed(futures):
            key = futures[future]
            try:
                cache[str(key)] = future.result()
            except RuntimeError as exc:
                logger.error("id %d: %s", key, exc)
            done += 1
            if done % checkpoint_every == 0:
                save_cache(cache)
                logger.info("MT progress: %d/%d", done, len(todo))
                print(f"progress {done}/{len(todo)}", flush=True)
    save_cache(cache)
    return cache


def _normalize(text: str) -> str:
    """Lower-case, strip format tokens and punctuation for fair comparison."""
    text = _TOKEN_RE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def compare(cache: dict[str, str], russian: dict[int, str],
            official: dict[int, str], targets: list[int]) -> list[ComparisonRow]:
    rows = []
    for key in targets:
        mt = cache.get(str(key))
        ref = official.get(key)
        if mt is None or ref is None or not ref.strip():
            continue
        ratio = difflib.SequenceMatcher(None, _normalize(mt), _normalize(ref)).ratio()
        rows.append(ComparisonRow(key, russian.get(key, ""), mt, ref, round(ratio, 3)))
    rows.sort(key=lambda r: r.similarity)
    return rows


def write_report(rows: list[ComparisonRow]) -> None:
    REPORT_TSV.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_TSV.open("w", encoding="utf-8", newline="") as fh:
        fh.write("id\tsimilarity\tmachine_translation\tofficial_english\trussian_source\n")
        for r in rows:
            fh.write(f"{r.key}\t{r.similarity}\t{r.machine}\t{r.official}\t{r.russian}\n")

    if rows:
        sims = [r.similarity for r in rows]
        buckets = {
            "identical_or_near (>=0.9)": sum(1 for s in sims if s >= 0.9),
            "close (0.7-0.9)": sum(1 for s in sims if 0.7 <= s < 0.9),
            "divergent (0.4-0.7)": sum(1 for s in sims if 0.4 <= s < 0.7),
            "very_different (<0.4)": sum(1 for s in sims if s < 0.4),
        }
        summary = {
            "compared": len(rows),
            "mean_similarity": round(sum(sims) / len(sims), 3),
            "median_similarity": round(sorted(sims)[len(sims) // 2], 3),
            "buckets": buckets,
        }
    else:
        summary = {"compared": 0}
    REPORT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Detail: {REPORT_TSV} ({len(rows)} rows, sorted by divergence)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--russian", type=Path, default=DEFAULT_RUSSIAN)
    ap.add_argument("--old-english", type=Path, default=DEFAULT_OLD_ENGLISH,
                    help="English file whose gaps define the target ID set")
    ap.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE,
                    help="recovered official English file to compare MT against")
    ap.add_argument("--limit", type=int, default=None, help="translate only the first N missing IDs")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--compare-only", action="store_true", help="skip MT, only rebuild the report from cache")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    russian = parse_file(args.russian).entries
    old_english = parse_file(args.old_english).entries
    reference = parse_file(args.reference).entries

    targets = sorted(russian.keys() - old_english.keys())
    if args.limit:
        targets = targets[: args.limit]
    print(f"Target IDs (missing in old English file): {len(targets)}")

    cache = load_cache() if args.compare_only else translate_missing(
        russian, targets, workers=args.workers)
    write_report(compare(cache, russian, reference, targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
