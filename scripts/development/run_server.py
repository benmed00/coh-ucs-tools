#!/usr/bin/env python3
"""Start the local dev server (API + SPA monolith)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "coh_ucs_tools.web.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
    ]
    print("Starting:", " ".join(cmd))
    print("Open http://127.0.0.1:8000/")
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
