# Backlog

Prioritized roadmap for the CoH UCS Toolkit. Priorities: **P1** (next up,
high value), **P2** (valuable, not urgent), **P3** (nice to have / research).
Effort: S (< half a day), M (a few days), L (a week or more).

## P1 — next up

| Item | Description | Effort | Status |
|---|---|---|---|
| In-game verification checklist | Scripted checklist of known-bad IDs (`$559200`, `$9419700`, ToV menus, OF campaign strings) to verify after installing `complete.ucs`; document screenshots/expected text | S | Open |
| Fix `statistics.py` stdlib shadowing | Renamed to `ucs_stats.py`; all imports updated | S | **Done** |
| Packaging (`pyproject.toml`) | Proper package layout (`coh_ucs_tools/`), console entry point (`coh-ucs`), `pip install .`; fixes the stdlib-shadowing issue as a side effect | M | Open |
| CI — GitHub Actions | Workflow running `unittest` on a Python 3.11/3.12/3.13 matrix (Windows + Ubuntu), plus a lint step | S | **Done** (3.12/ubuntu) |
| No-BOM heuristics hardening | The strict UTF-16-LE probe accepts some non-UCS binaries; add NUL-distribution and printable-ratio checks, fuzz with random bytes, add tests | M | Open |

## P2 — valuable

| Item | Description | Effort | Status |
|---|---|---|---|
| SGA archive parser | Read Relic SGA archives directly so locale data can be extracted from depots/installs without manual unpacking (the CE's local locale `.sga` files are stubs, but depot copies are not) | L | **Stub** (SGA scan lists archives, flags stubs &lt;10 KB) |
| Web app: persistence | Store uploads/merge results in SQLite instead of process memory + temp dir; survive restarts | M | **Done** |
| Web app: auth | API-key or session auth for non-local deployments; rate-limit uploads | M | **Partial** (`UCS_API_KEY` middleware) |
| Web app: deployment | Dockerfile + docker-compose, reverse-proxy notes, `uvicorn` production settings | S | **Done** |
| Glossary-aware MT comparison | Feed a CoH glossary into the similarity metric | M | **Done** |
| Locale coverage for other languages | Run the compare/merge pipeline for French, German, Spanish, Polish, etc. CE locales; publish per-language coverage tables | M | **Partial** (languages hub API + UI) |

## P3 — nice to have / research

| Item | Description | Effort | Status |
|---|---|---|---|
| CoH2 / DoW UCS variants | Support the UCS dialects of other Relic titles (Dawn of War I/II, CoH2 — different key ranges, possible format deviations); pluggable game-variant profiles | L | **Stub** (`GET /api/games` profiles) |
| Diff/patch mode | Generate and apply `.ucs` diffs between versions (useful for tracking patch-to-patch localization changes) | M | **Partial** (diff API + patch builder subset download) |
| Duplicate-policy verification | Empirically verify the "last occurrence wins" assumption against the actual game engine (inject a crafted duplicate and observe) | S | Open |
| Streaming parser | Constant-memory parsing for very large files (current files are ~2 MB, so this is purely defensive) | M | Open |
| Web app: Three.js frontend polish | Visual coverage map / key-range visualization improvements in the static frontend | M | **Partial** (locale globe pins, ranges heatmap, Chart.js donuts) |
| Translation-memory export | Export common-key RU/EN pairs as TMX for use in CAT tools | S | Open |
