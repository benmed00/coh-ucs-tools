"""Shared text validation helpers for UCS values."""

from __future__ import annotations

import unicodedata

_ALLOWED_CONTROLS = {"\t"}


def bad_characters(value: str) -> list[str]:
    """Return descriptions of characters that break UTF-16 or indicate corruption."""
    problems = []
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            problems.append(f"lone surrogate U+{code:04X}")
        elif unicodedata.category(ch) == "Cc" and ch not in _ALLOWED_CONTROLS:
            problems.append(f"control character U+{code:04X}")
    return problems
