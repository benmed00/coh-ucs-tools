"""PO/Gettext import/export for UCS files (msgctxt = numeric id)."""

from __future__ import annotations

import re
from pathlib import Path

from coh_ucs_tools.core.parser import UcsDocument, parse_file, write_file

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
        '"Content-Type: text/plain; charset=UTF-8\\n"',
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


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_tmx(doc: UcsDocument, *, source_lang: str = "en", target_lang: str = "en") -> str:
    """Export UCS entries to TMX 1.4 (tuid = numeric id) for CAT tools."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE tmx SYSTEM "tmx14.dtd">',
        '<tmx version="1.4">',
        f'  <header creationtool="coh-ucs-tools" srclang="{_escape_xml(source_lang)}" '
        f'adminlang="en" datatype="plaintext" segtype="sentence"/>',
        "  <body>",
    ]
    for key, value in doc.sorted_entries():
        lines.append(f'    <tu tuid="{key}">')
        lines.append(
            f'      <tuv xml:lang="{_escape_xml(source_lang)}">'
            f"<seg>{_escape_xml(value)}</seg></tuv>"
        )
        lines.append(
            f'      <tuv xml:lang="{_escape_xml(target_lang)}">'
            f"<seg>{_escape_xml(value)}</seg></tuv>"
        )
        lines.append("    </tu>")
    lines.extend(["  </body>", "</tmx>"])
    return "\n".join(lines) + "\n"


_TU_RE = re.compile(
    r'<tu\s+tuid="(\d+)"[^>]*>.*?<tuv[^>]*xml:lang="[^"]*"[^>]*>\s*<seg>(.*?)</seg>',
    re.DOTALL,
)


def import_tmx(text: str, *, target_lang: str | None = None) -> dict[int, str]:
    """Parse TMX text; return id -> target string (second tuv when two present)."""
    entries: dict[int, str] = {}
    for m in _TU_RE.finditer(text):
        key = int(m.group(1))
        seg = m.group(2)
        seg = (
            seg.replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&amp;", "&")
        )
        entries[key] = seg
    if target_lang and entries:
        # Re-parse per-tu for explicit target lang when multiple tuvs differ
        tu_blocks = re.split(r"<tu\s+", text)
        refined: dict[int, str] = {}
        for block in tu_blocks[1:]:
            uid_m = re.match(r'tuid="(\d+)"', block)
            if not uid_m:
                continue
            key = int(uid_m.group(1))
            tuvs = re.findall(
                r'<tuv[^>]*xml:lang="([^"]*)"[^>]*>\s*<seg>(.*?)</seg>',
                block,
                re.DOTALL,
            )
            chosen = None
            for lang, seg in tuvs:
                if lang.lower().startswith(target_lang.lower()):
                    chosen = seg
                    break
            if chosen is None and tuvs:
                chosen = tuvs[-1][1]
            if chosen is not None:
                refined[key] = (
                    chosen.replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&quot;", '"')
                    .replace("&amp;", "&")
                )
        if refined:
            entries = refined
    return entries


def tmx_to_ucs(
    tmx_path: Path | str,
    out_path: Path | str,
    *,
    template: UcsDocument | None = None,
    target_lang: str | None = None,
) -> Path:
    text = Path(tmx_path).read_text(encoding="utf-8")
    entries = import_tmx(text, target_lang=target_lang)
    enc = template.encoding if template else "utf-16-le"
    bom = template.has_bom if template else True
    nl = template.newline if template else "\r\n"
    trail = template.trailing_newline if template else True
    return write_file(
        out_path, sorted(entries.items()), encoding=enc,
        add_bom=bom, newline=nl, trailing_newline=trail, overwrite=True,
    )
