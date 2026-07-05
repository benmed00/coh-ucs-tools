# API Reference

Two surfaces expose the same functionality:

1. the **Python API** — the importable modules (`parser`, `validator`,
   `statistics`, `merge`), and
2. the **REST API** — the FastAPI application in `webapp/`, self-documented
   with Swagger/OpenAPI at `/docs`.

- [Python API](#python-api)
  - [parser](#parser)
  - [validator](#validator)
  - [statistics](#statistics)
  - [merge](#merge)
- [REST API](#rest-api)

## Python API

All modules use only the standard library (`chardet` is an optional
fallback). All types are dataclasses with full type hints.

### parser

#### Types

```python
@dataclass(frozen=True)
class UcsEntry:
    key: int
    value: str
    line_number: int      # 1-based

@dataclass(frozen=True)
class InvalidLine:
    line_number: int
    raw: str
    reason: str

@dataclass
class UcsDocument:
    path: Optional[Path]
    entries: dict[int, str]           # duplicates collapsed, last wins
    all_entries: list[UcsEntry]       # every valid line, file order
    duplicates: dict[int, list[int]]  # key -> line numbers
    invalid_lines: list[InvalidLine]
    encoding: str                     # e.g. "utf-16-le"
    has_bom: bool
    newline: str                      # "\r\n" or "\n"
    trailing_newline: bool
    empty_line_count: int

    keys: list[int]                              # property, sorted
    def sorted_entries(self) -> list[tuple[int, str]]: ...
```

#### Functions

```python
def detect_encoding(raw: bytes) -> tuple[str, bool]
```
Returns `(encoding, has_bom)`. Detection order: UTF-16 BOM (LE/BE) → strict
UTF-16-LE probe → `chardet` (if installed) → UTF-8 fallback.

```python
def parse_file(path: Path | str) -> UcsDocument
def parse_bytes(raw: bytes, path: Optional[Path] = None) -> UcsDocument
def parse_text(text: str, path: Optional[Path] = None) -> UcsDocument
```
Parse a UCS file / raw bytes / decoded text. Malformed lines land in
`invalid_lines` (never silently dropped); duplicate keys are collapsed
last-wins and recorded in `duplicates`.

```python
def serialize(entries: Iterable[tuple[int, str]], *,
              newline: str = "\r\n", trailing_newline: bool = True) -> str
```
Serialize `(id, value)` pairs to UCS text (no BOM).

```python
def write_file(path: Path | str, entries: Iterable[tuple[int, str]], *,
               encoding: str = "utf-16-le", add_bom: bool = True,
               newline: str = "\r\n", trailing_newline: bool = True,
               overwrite: bool = False) -> Path
```
Write a UCS file with the on-disk conventions (UTF-16-LE + BOM + CRLF by
default). **Raises `FileExistsError`** if the target exists and
`overwrite` is not set — originals can never be clobbered by accident.

#### Example

```python
from parser import parse_file, write_file

doc = parse_file(r"C:\...\RelicCOH.English.ucs")
print(len(doc.entries), doc.encoding, doc.has_bom)   # 8578 utf-16-le True
print(doc.entries[17])                                # text for id 17

write_file("out.ucs", doc.sorted_entries())           # round-trip
```

### validator

```python
class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"

@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str            # see table below
    key: Optional[int]
    message: str

@dataclass
class ValidationResult:
    issues: list[Issue]
    errors: list[Issue]    # property
    warnings: list[Issue]  # property
    ok: bool               # property: no errors
```

```python
def validate(doc: UcsDocument,
             reference: Optional[UcsDocument] = None) -> ValidationResult
```

| Code | Severity | Meaning |
|---|---|---|
| `invalid-line` | error | structurally broken line (no tab / non-numeric key) |
| `duplicate-id` | error | same ID defined on multiple lines |
| `bad-character` | error | lone UTF-16 surrogate or disallowed control character |
| `empty-value` | warning | `<id><TAB>` with no text |
| `missing-id` | warning | ID present in `reference` but absent here |

Every value is also round-tripped through strict UTF-16-LE encoding.

```python
from parser import parse_file
from validator import validate

result = validate(parse_file("english.ucs"), reference=parse_file("russian.ucs"))
print(result.ok, len(result.errors), len(result.warnings))
for issue in result.errors:
    print(issue)   # [ERROR] duplicate-id (id 42): defined on lines 3, 9
```

### statistics

> Note: this module shadows the stdlib `statistics` module when the repo
> root is on `sys.path` — a rename is on the backlog.

```python
def compress_ranges(keys: Iterable[int]) -> list[str]
```
`[1, 2, 3, 7, 9, 10]` → `['1-3', '7', '9-10']`. Used for the
missing-ID exports (e.g. `559200-559650`).

```python
@dataclass(frozen=True)
class Comparison:
    russian: UcsDocument
    english: UcsDocument

    missing_in_english: list[int]   # property
    missing_in_russian: list[int]   # property
    common_keys: list[int]          # property
    def statistics(self) -> dict: ...
```
`statistics()` returns totals, duplicates, invalid lines, empty values,
missing counts and `coverage_percent` (against the union of both key sets)
for each side.

```python
def generate_report(comparison: Comparison,
                    out_dir: Path | str = Path("report")) -> Path
```
Writes the seven report files (`russian_keys.txt`, `english_keys.txt`,
`missing_in_english.txt`, `missing_in_russian.txt`, `duplicate_keys.txt`,
`invalid_lines.txt`, `statistics.json`).

```python
from parser import parse_file
from statistics import Comparison, generate_report

comp = Comparison(parse_file("russian.ucs"), parse_file("english.ucs"))
print(comp.statistics()["english"]["coverage_percent"])   # 38.42
generate_report(comp)                                     # -> report/
```

### merge

```python
PLACEHOLDER = "<MISSING>"

@dataclass
class MergeResult:
    entries: dict[int, str]
    added_placeholders: list[int]   # IDs that were added (sorted)
    preserved: int                  # count of untouched target entries
    output_path: Path | None
```

```python
def merge_documents(target: UcsDocument, source: UcsDocument,
                    placeholder: str = PLACEHOLDER,
                    fill_from_source: bool = False) -> MergeResult
```
Every `target` entry is kept verbatim. IDs that exist only in `source` are
added with the placeholder, or — with `fill_from_source=True` — with the
source text copied verbatim. **No translation is ever generated.**

```python
def merge_and_write(target: UcsDocument, source: UcsDocument,
                    output: Path | str | None = None,
                    placeholder: str = PLACEHOLDER,
                    overwrite_output: bool = True,
                    fill_from_source: bool = False) -> MergeResult
```
Merge and write numerically sorted output using the target's encoding
conventions. **Raises `ValueError`** if `output` resolves to either input
file — originals are never overwritten. Default output:
`<target-stem>.merged.ucs` in the current directory.

```python
from parser import parse_file
from merge import merge_and_write

result = merge_and_write(parse_file("english.ucs"), parse_file("russian.ucs"))
print(result.preserved, len(result.added_placeholders), result.output_path)
```

## REST API

The FastAPI app in `webapp/` wraps the modules above — no logic is
reimplemented. Run it and open the **interactive Swagger UI at
[`/docs`](http://127.0.0.1:8000/docs)** (OpenAPI JSON at `/openapi.json`):

```powershell
python -m uvicorn webapp.main:app --reload
```

All endpoints are prefixed with `/api`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/files` | Upload a `.ucs` file (multipart, ≤ 20 MB); parsed immediately, returns file id + summary |
| `GET` | `/api/files` | List all stored files (uploads, built-in versions, merge results) |
| `GET` | `/api/files/{file_id}` | Summary for one file (keys, duplicates, invalid lines, encoding…) |
| `DELETE` | `/api/files/{file_id}` | Delete an upload/generated file (built-in versions are read-only → 403) |
| `GET` | `/api/files/{file_id}/entries` | Paginated, numerically sorted entries; `search=` filters by id or text, `regex=true` for regular expressions |
| `GET` | `/api/files/{file_id}/validate` | Full validation (duplicate ids, invalid lines, empty values, bad characters, UTF-16 round-trip) |
| `GET` | `/api/compare?a={id}&b={id}` | Coverage statistics for two files + missing-id sets compressed into ranges |
| `POST` | `/api/merge` | Merge `source_id` into `target_id` (`mode`: `placeholder` or `fill_from_source`); returns a download id |
| `GET` | `/api/downloads/{file_id}` | Download any stored file with a proper filename |
| `GET` | `/api/versions` | Built-in registry of known CoH1 UCS versions (THQ retail, CE Russian, NSV English, complete build) |
| `GET` | `/api/versions/{version_id}/download` | Download a registered version (served from read-only server-side copies) |
| `GET` | `/api/tools` | Curated external tools & references (Mod Studio, DepotDownloader, SteamDB…) |
| `GET` | `/api/health` | Health check: status, file and version counts |

### Extended endpoints (v1.1)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/files/{id}/diff/{other}?filter=&offset=&limit=` | Entry-level diff (changed/missing/empty/token_mismatch) |
| `GET` | `/api/compare/{a}/{b}/ranges` | Missing-id heatmap buckets |
| `GET` | `/api/files/{id}/lint` | Format-token + script lint summary |
| `GET` | `/api/files/{id}/issues`, `…/issues.csv` | Duplicates + invalid lines (CSV export) |
| `GET` | `/api/files/{id}/fingerprint` | sha256, BOM, encoding, NSV match |
| `GET` | `/api/languages` | Localization hub cards (EN/FR/AR/RU) |
| `POST` | `/api/merge/preview` | Preview first N merge changes |
| `GET` | `/api/install/detect` | Scan known install paths + PowerShell commands |
| `POST` | `/api/mt/queue`, `GET …/status`, `GET …/report` | Background MT QA jobs |
| `GET`/`PUT` | `/api/glossary` | MT post-processing glossary (`webapp/storage/glossary.json`) |
| `GET` | `/api/versions/timeline` | Version history timeline |
| `GET` | `/api/depots`, `/api/sources` | Steam depot cards + community registry |
| `GET` | `/api/search/global`, `/api/crossref/{key}` | Cross-version search + cross-reference |
| `GET`/`POST`/`DELETE` | `/api/bookmarks` | Persisted QA id list |
| `POST` | `/api/batch/compare`, `GET …/{job_id}/zip` | All-pairs comparison zip |
| `GET` | `/api/export/openapi-client` | curl/Python usage snippets |
| `GET` | `/api/sga/scan?install_path=` | List `.sga` archives (stub flag &lt;10 KB) |
| `GET` | `/api/games` | Game variant profiles (CoH1/CoH2/DoW stubs) |
| `POST` | `/api/patch/build` | Subset UCS download by id ranges |
| `GET` | `/api/audit` | Recent operations log (no string content) |

Optional env `UCS_API_KEY` enables `X-API-Key` header check on `/api/*`.
Uploads older than 24 h are purged on startup.

### ucs_analysis

```python
def diff_entries(a, b, filters) -> list[DiffRow]
def token_linter(value) -> list[TokenIssue]
def compare_tokens(a_val, b_val) -> Optional[TokenIssue]
def script_detect(value) -> list[ScriptFinding]
def fingerprint_file(path | bytes) -> FileFingerprint
def subset_by_ranges(entries, ranges) -> dict[int, str]
def fuzzy_search(query, entries, threshold) -> list[tuple[int, str, float]]
```

Error responses use a consistent JSON body (`ErrorResponse`); uploads over
20 MB return `413`, unknown ids `404`, invalid regexes `400`.
