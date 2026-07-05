"""PO/Gettext import/export for UCS files (msgctxt = numeric id)."""

from __future__ import annotations

import re
from pathlib import Path

from parser import UcsDocument, parse_file, write_file

_MSGCTXT_RE = re.compile(r'^msgctxt\s+"(.*)"\s*$', re.MULTILINE)
_MSGID_RE = re.compile(r'^msgid\s+"(.*)"\s*$', re.MULTILINE)
_MSGSTR_RE = re.compile(r'^msgstr\s+"(.*)"\s*$', re.MULTILINE)


def _escape_po(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _unescape_po(text: str) -> str:
    return text.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def export_po(doc: UcsDocument, header: str = "") -> str:
    """Export UCS entries to GNU gettext .po format (id as msgctxt)."""
    lines = [
        'msgid ""',
        'msgstr ""',
        f'"Content-Type: text/plain; charset=UTF-8\\n"',
        "",
    ]
    if header:
        lines.insert(0, f"# {header}")
    for key, value in doc.sorted_entries():
        lines.append(f'msgctxt "{key}"')
        lines.append(f'msgid "{_escape_po(value)}"')
        lines.append(f'msgstr "{_escape_po(value)}"')
        lines.append("")
    return "\n".join(lines)


def import_po(text: str) -> dict[int, str]:
    """Parse .po text; return id -> translated string (msgctxt = UCS id)."""
    entries: dict[int, str] = {}
    blocks = re.split(r"\n\n+", text)
    for block in blocks:
        if "msgctxt" not in block:
            continue
        ctx_m = _MSGCTXT_RE.search(block)
        str_m = _MSGSTR_RE.search(block)
        if not ctx_m:
            continue
        try:
            key = int(ctx_m.group(1))
        except ValueError:
            continue
        value = _unescape_po(str_m.group(1)) if str_m else ""
        entries[key] = value
    return entries


def po_to_ucs(po_path: Path | str, out_path: Path | str, *,
              template: UcsDocument | None = None) -> Path:
    """Import .po and write UCS, preserving encoding from template if given."""
    text = Path(po_path).read_text(encoding="utf-8")
    entries = import_po(text)
    enc = template.encoding if template else "utf-16-le"
    bom = template.has_bom if template else True
    nl = template.newline if template else "\r\n"
    trail = template.trailing_newline if template else True
    return write_file(out_path, sorted(entries.items()), encoding=enc,
                      add_bom=bom, newline=nl, trailing_newline=trail,
                      overwrite=True)


def ucs_to_po(ucs_path: Path | str, po_path: Path | str) -> Path:
    doc = parse_file(ucs_path)
    Path(po_path).write_text(export_po(doc, header=str(ucs_path)), encoding="utf-8")
    return Path(po_path)
