# Contributing

Thanks for helping improve the CoH UCS Toolkit. This document covers dev
setup, running tests, code style, and how to add support for another game.

## Dev setup

Requirements: Python 3.12+ on Windows (the toolkit is developed and tested
on Windows; the core is OS-independent).

```powershell
git clone <your-fork> coh-ucs-tools
cd coh-ucs-tools

# optional but recommended
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install package with web extras (FastAPI, uvicorn, chardet)
pip install -e ".[web]"

# on Windows, make console output unicode-safe
$env:PYTHONIOENCODING = "utf-8"
```

## Running the tests

```powershell
pip install -e ".[web]" pytest coverage
python -m pytest tests/ -v
```

All tests must pass before you open a pull request. The suite uses **pytest**
(202+ cases). Add tests for every behaviour change; parser/writer changes need
a round-trip test.

## Code style

* **Stdlib-only core.** `coh_ucs_tools.core.*`, `coh_ucs_tools.analysis.*`,
  and `coh_ucs_tools.cli` must not gain required third-party dependencies.
  `chardet` stays optional (import inside a `try`/`except ImportError`).
  Only `coh_ucs_tools.web` and `coh_ucs_tools.tools.translate` may use
  external packages, declared in `pyproject.toml` optional extras.
* **Dataclasses + typing.** Public data structures are `@dataclass`es
  (frozen where value-like); all public functions carry full type hints and
  docstrings. `from __future__ import annotations` at the top of modules.
* **Never destroy user data.** Writers must refuse to overwrite existing
  files unless explicitly told to (`overwrite=True`), and must never write
  on top of an input file. Keep these guarantees in anything you add.
* **No silent drops.** Malformed input is recorded (line number, raw text,
  reason) and surfaced in validation/reports — never discarded.
* **No invented translations.** Merge modes may copy text verbatim or emit
  `<MISSING>` placeholders; machine translation is for QA comparison only
  and must never end up in a generated game file.
* Logging via `logging.getLogger(__name__)`, not `print` (the CLI's user
  output is the exception).

## Adding a game variant (e.g. CoH2, Dawn of War)

Other Relic titles use UCS dialects that differ in key ranges and
occasionally in conventions. To add one:

1. **Capture the format first.** Obtain real files, verify encoding, BOM,
   newline style, separator and duplicate behaviour byte-for-byte (see the
   findings table in the README for what to check). Document the findings
   in the PR description and in `docs/`.
2. Put variant-specific constants (default paths, expected key ranges,
   quirks) behind a profile — do not sprinkle `if game == ...` checks
   through the parser. If the line grammar itself differs, extend
   `parse_text` with a strategy rather than forking the module.
3. Add fixture-based tests with small hand-crafted samples for the new
   variant (never commit real game files — they are copyrighted).
4. Update the version registry in `coh_ucs_tools.web.deps` (`KNOWN_VERSIONS`) if the
   variant should appear in the web app.

## Copyrighted content

Never commit game localization files or anything containing game text:
`.ucs` files from an install, the recovered NSV file (`downloads/`), the MT
cache (`downloads/mt_cache.json`), or generated merges. `.gitignore`
already excludes these paths — do not work around it.

## Commits and pull requests

* Conventional commit style: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`,
  `chore:` with a concise imperative subject.
* One logical change per PR; include the *why* in the description.
* PRs must keep the test suite green.

## GitHub Wiki

User-facing UI guides and screenshots live in the
[project wiki](https://github.com/benmed00/coh-ucs-tools/wiki). When you add
SPA routes or change workflows, update the matching wiki page and run
`python scripts/wiki_screenshots.py` to refresh screenshots (see wiki
[Documentation Map](https://github.com/benmed00/coh-ucs-tools/wiki/Documentation-Map)).
Repo `docs/*.md` files remain the canonical reference for API signatures,
deployment secrets, and the full project report.
