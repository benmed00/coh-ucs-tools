"""Validation for parsed UCS documents.

Checks performed:

* duplicate IDs (same key on multiple lines)
* missing IDs (gaps relative to a reference document, when given)
* empty values
* characters not encodable in UTF-16 (lone surrogates) and control
  characters that indicate line corruption
* structurally invalid lines carried over from the parser
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from parser import UcsDocument
from merge import PLACEHOLDER

logger = logging.getLogger(__name__)

#: Control characters that are legitimate inside a UCS value.
_ALLOWED_CONTROLS = {"\t"}


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    key: Optional[int]
    message: str

    def __str__(self) -> str:
        where = f"id {self.key}" if self.key is not None else "file"
        return f"[{self.severity.value.upper()}] {self.code} ({where}): {self.message}"


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, severity: Severity, code: str, key: Optional[int], message: str) -> None:
        self.issues.append(Issue(severity, code, key, message))


_TOKEN_RE = re.compile(r"%\d[A-Za-z]*%")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_LATIN_LOCALES = frozenset({"english", "french", "german", "spanish", "italian", "polish", "latin"})


def _token_count(value: str) -> int:
    return len(_TOKEN_RE.findall(value))


def _bad_characters(value: str) -> list[str]:
    """Return descriptions of characters that break UTF-16 or indicate corruption."""
    problems = []
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            problems.append(f"lone surrogate U+{code:04X}")
        elif unicodedata.category(ch) == "Cc" and ch not in _ALLOWED_CONTROLS:
            problems.append(f"control character U+{code:04X}")
    return problems


def validate(
    doc: UcsDocument,
    reference: Optional[UcsDocument] = None,
    *,
    locale: Optional[str] = None,
) -> ValidationResult:
    """Validate ``doc``. If ``reference`` is given, also report IDs present in
    the reference but missing from ``doc``, and token-count mismatches."""
    result = ValidationResult()

    for line in doc.invalid_lines:
        result.add(Severity.ERROR, "invalid-line", None,
                   f"line {line.line_number}: {line.reason}: {line.raw[:80]!r}")

    for key, line_numbers in sorted(doc.duplicates.items()):
        result.add(Severity.ERROR, "duplicate-id", key,
                   f"defined on lines {', '.join(map(str, line_numbers))}")

    loc = (locale or "").lower()
    for key, value in doc.sorted_entries():
        if value == "":
            result.add(Severity.WARNING, "empty-value", key, "value is empty")
            continue
        if value == PLACEHOLDER or PLACEHOLDER in value:
            result.add(Severity.WARNING, "missing-literal", key,
                       f"contains {PLACEHOLDER!r} placeholder")
        if loc in _LATIN_LOCALES and _CYRILLIC_RE.search(value):
            result.add(Severity.WARNING, "cyrillic-in-latin-locale", key,
                       "Cyrillic characters in a Latin-script locale file")
        for problem in _bad_characters(value):
            result.add(Severity.ERROR, "bad-character", key, problem)

    try:
        # Round-trip check: every value must survive strict UTF-16 encoding.
        for key, value in doc.sorted_entries():
            value.encode("utf-16-le", errors="strict")
    except UnicodeEncodeError as exc:  # pragma: no cover - caught above per char
        result.add(Severity.ERROR, "utf16-encode", key, str(exc))

    if reference is not None:
        missing = sorted(reference.entries.keys() - doc.entries.keys())
        for key in missing:
            result.add(Severity.WARNING, "missing-id", key,
                       f"present in {reference.path.name if reference.path else 'reference'} but missing here")
        for key in sorted(doc.entries.keys() & reference.entries.keys()):
            a_tok = _token_count(doc.entries[key])
            b_tok = _token_count(reference.entries[key])
            if a_tok != b_tok:
                result.add(Severity.WARNING, "token-parity", key,
                           f"format token count mismatch ({a_tok} vs {b_tok} in reference)")

    logger.info("Validation of %s: %d error(s), %d warning(s)",
                doc.path.name if doc.path else "<memory>",
                len(result.errors), len(result.warnings))
    return result
