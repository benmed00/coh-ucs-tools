"""One-time migration: flat root modules -> src/coh_ucs_tools package."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src" / "coh_ucs_tools"

MOVES: list[tuple[str, str]] = [
    ("parser.py", "core/parser.py"),
    ("merge.py", "core/merge.py"),
    ("validator.py", "core/validator.py"),
    ("ucs_stats.py", "analysis/stats.py"),
    ("ucs_analysis.py", "analysis/diff.py"),
    ("patch_chain.py", "analysis/patch_chain.py"),
    ("po_io.py", "io/po.py"),
    ("sga_reader.py", "io/sga.py"),
    ("game_profiles.py", "profiles/game.py"),
    ("locale_build.py", "locale/build.py"),
    ("locale_coverage.py", "locale/coverage.py"),
    ("translate.py", "tools/translate.py"),
    ("depot_downloader.py", "tools/depot.py"),
    ("verification_checklist.py", "tools/verification.py"),
    ("duplicate_probe.py", "tools/duplicate_probe.py"),
    ("build_french.py", "locale/builders/french.py"),
    ("build_german.py", "locale/builders/german.py"),
    ("build_spanish.py", "locale/builders/spanish.py"),
    ("build_italian.py", "locale/builders/italian.py"),
    ("build_polish.py", "locale/builders/polish.py"),
    ("build_arabic.py", "locale/builders/arabic.py"),
    ("cli.py", "cli/__init__.py"),
]

IMPORT_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bfrom parser import\b", "from coh_ucs_tools.core.parser import"),
    (r"\bfrom merge import\b", "from coh_ucs_tools.core.merge import"),
    (r"\bfrom validator import\b", "from coh_ucs_tools.core.validator import"),
    (r"\bfrom ucs_stats import\b", "from coh_ucs_tools.analysis.stats import"),
    (r"\bfrom ucs_analysis import\b", "from coh_ucs_tools.analysis.diff import"),
    (r"\bfrom patch_chain import\b", "from coh_ucs_tools.analysis.patch_chain import"),
    (r"\bfrom po_io import\b", "from coh_ucs_tools.io.po import"),
    (r"\bfrom sga_reader import\b", "from coh_ucs_tools.io.sga import"),
    (r"\bfrom game_profiles import\b", "from coh_ucs_tools.profiles.game import"),
    (r"\bfrom locale_build import\b", "from coh_ucs_tools.locale.build import"),
    (r"\bfrom locale_coverage import\b", "from coh_ucs_tools.locale.coverage import"),
    (r"\bfrom translate import\b", "from coh_ucs_tools.tools.translate import"),
    (r"\bfrom depot_downloader import\b", "from coh_ucs_tools.tools.depot import"),
    (r"\bfrom verification_checklist import\b", "from coh_ucs_tools.tools.verification import"),
    (r"\bfrom duplicate_probe import\b", "from coh_ucs_tools.tools.duplicate_probe import"),
    (r"\bfrom build_french import\b", "from coh_ucs_tools.locale.builders.french import"),
    (r"\bfrom build_german import\b", "from coh_ucs_tools.locale.builders.german import"),
    (r"\bfrom build_spanish import\b", "from coh_ucs_tools.locale.builders.spanish import"),
    (r"\bfrom build_italian import\b", "from coh_ucs_tools.locale.builders.italian import"),
    (r"\bfrom build_polish import\b", "from coh_ucs_tools.locale.builders.polish import"),
    (r"\bfrom build_arabic import\b", "from coh_ucs_tools.locale.builders.arabic import"),
    (r"\bfrom cli import\b", "from coh_ucs_tools.cli import"),
    (r":mod:`parser`", ":mod:`coh_ucs_tools.core.parser`"),
    (r":mod:`merge`", ":mod:`coh_ucs_tools.core.merge`"),
    (r":mod:`validator`", ":mod:`coh_ucs_tools.core.validator`"),
    (r":mod:`statistics`", ":mod:`coh_ucs_tools.analysis.stats`"),
    (r":mod:`ucs_stats`", ":mod:`coh_ucs_tools.analysis.stats`"),
    (r":mod:`ucs_analysis`", ":mod:`coh_ucs_tools.analysis.diff`"),
    (r":mod:`cli`", ":mod:`coh_ucs_tools.cli`"),
]

WEBAPP_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bfrom webapp\.", "from coh_ucs_tools.web."),
    (r"\bimport webapp\b", "import coh_ucs_tools.web"),
    (r"webapp\.main:app", "coh_ucs_tools.web.main:app"),
    (r"webapp/static", "src/coh_ucs_tools/web/static"),
    (r"webapp\\static", "src/coh_ucs_tools/web/static"),
]


def rewrite_imports(text: str) -> str:
    for pattern, repl in IMPORT_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


def rewrite_webapp_refs(text: str) -> str:
    for pattern, repl in WEBAPP_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


def copy_and_rewrite(src_rel: str, dst_rel: str) -> None:
    src = ROOT / src_rel
    dst = SRC / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8")
    content = rewrite_imports(content)
    dst.write_text(content, encoding="utf-8")
    print(f"  {src_rel} -> {dst_rel}")


def touch_init(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def migrate_core_modules() -> None:
    print("Migrating core modules...")
    for src, dst in MOVES:
        copy_and_rewrite(src, dst)


def migrate_webapp() -> None:
    print("Migrating webapp...")
    web_src = ROOT / "webapp"
    web_dst = SRC / "web"
    if web_dst.exists():
        shutil.rmtree(web_dst)
    shutil.copytree(web_src, web_dst, ignore=shutil.ignore_patterns("__pycache__", "storage", "data"))
    for py in web_dst.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        text = rewrite_imports(text)
        py.write_text(text, encoding="utf-8")
    print("  webapp/ -> src/coh_ucs_tools/web/")


def create_inits() -> None:
    pkg = '"""CoH UCS Toolkit."""\n\n__version__ = "1.0.0"\n'
    touch_init(SRC / "__init__.py", pkg)
    for sub in ("core", "analysis", "io", "profiles", "locale", "locale/builders", "tools", "cli", "web", "web/api"):
        touch_init(SRC / sub / "__init__.py", f'"""coh_ucs_tools.{sub.replace("/", ".")}"""\n')


def rewrite_tree(root: Path, extra: list[tuple[str, str]] | None = None) -> None:
    patterns = IMPORT_REPLACEMENTS + (extra or [])
    for path in root.rglob("*"):
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".toml", ".txt"}:
            continue
        if "migrate_to_src" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        new = text
        for pattern, repl in patterns:
            new = re.sub(pattern, repl, new)
        new = rewrite_webapp_refs(new)
        if new != text:
            path.write_text(new, encoding="utf-8")


def main() -> None:
    migrate_core_modules()
    migrate_webapp()
    create_inits()
    print("Rewriting tests and scripts...")
    rewrite_tree(ROOT / "tests")
    rewrite_tree(ROOT / "scripts")
    rewrite_tree(ROOT / "docs")
    for name in ("Dockerfile", "docker-compose.yml", "README.md", "CONTRIBUTING.md", ".github"):
        p = ROOT / name
        if p.is_file():
            rewrite_tree(ROOT, [])  # will hit single files via rglob below
    for path in [ROOT / "Dockerfile", ROOT / "docker-compose.yml", ROOT / "README.md", ROOT / "CONTRIBUTING.md"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for pattern, repl in IMPORT_REPLACEMENTS + WEBAPP_REPLACEMENTS:
                text = re.sub(pattern, repl, text)
            path.write_text(text, encoding="utf-8")
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        for pattern, repl in WEBAPP_REPLACEMENTS:
            text = re.sub(pattern, repl, text)
        wf.write_text(text, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
