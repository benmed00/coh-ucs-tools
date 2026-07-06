"""Legacy entry point — re-exports the FastAPI app from the package layout.

Prefer::

    python -m uvicorn coh_ucs_tools.web.main:app --host 127.0.0.1 --port 8000 --reload
"""

from coh_ucs_tools.web.main import app

__all__ = ["app"]
