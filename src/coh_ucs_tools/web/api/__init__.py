"""REST API router assembly."""

from .core import router
from .extended import ext_router

__all__ = ["router", "ext_router"]
