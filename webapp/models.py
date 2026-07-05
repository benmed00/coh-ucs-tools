"""Pydantic response/request models for the REST API (OpenAPI schema)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FileSummary(BaseModel):
    """Parse summary for a stored UCS file."""

    id: str = Field(description="Server-assigned file id", examples=["8f14e45fceea167a5a36dedd4bea2543"])
    name: str = Field(description="Original filename", examples=["RelicCOH.English.ucs"])
    kind: Literal["upload", "version", "generated"] = Field(description="How the file entered the store")
    size: int = Field(description="Size on disk in bytes")
    created_at: float = Field(description="Unix timestamp of registration")
    keys: int = Field(description="Unique entry count (last duplicate wins)", examples=[22523])
    duplicates: int = Field(description="Keys defined on more than one line")
    invalid_lines: int = Field(description="Lines that failed to parse")
    empty_values: int = Field(description="Entries whose value is the empty string")
    encoding: str = Field(description="Detected encoding", examples=["utf-16-le"])
    has_bom: bool = Field(description="True when the file starts with a BOM (FF FE)")
    newline: str = Field(description="Detected line ending convention", examples=["CRLF"])
    min_key: Optional[int] = Field(default=None, description="Smallest numeric id")
    max_key: Optional[int] = Field(default=None, description="Largest numeric id")


class FileListResponse(BaseModel):
    files: list[FileSummary]


class UploadResponse(BaseModel):
    """Returned after a successful multipart upload."""

    file: FileSummary
    message: str = Field(examples=["Parsed 22523 entries"])


class Entry(BaseModel):
    key: int = Field(examples=[559200])
    value: str = Field(examples=["Panzer IV Medium Tank"])


class EntriesPage(BaseModel):
    """One page of a (possibly filtered) entries listing."""

    file_id: str
    total: int = Field(description="Total entries matching the filter")
    offset: int
    limit: int
    search: Optional[str] = None
    regex: bool = False
    entries: list[Entry]


class ValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str = Field(examples=["duplicate-id", "empty-value", "bad-character"])
    key: Optional[int] = None
    message: str


class ValidationResponse(BaseModel):
    file_id: str
    ok: bool = Field(description="True when there are no errors (warnings allowed)")
    errors: int
    warnings: int
    issues: list[ValidationIssue]


class CompareSide(BaseModel):
    """Per-file statistics inside a comparison."""

    id: str
    name: str
    total_keys: int
    duplicated_keys: int
    invalid_lines: int
    empty_values: int
    missing_keys: int = Field(description="Keys present in the other file but not here")
    coverage_percent: float = Field(description="Share of the union key set covered", examples=[98.43])
    missing_ranges: list[str] = Field(description="Missing ids compressed to ranges", examples=[["559200-559650", "600100"]])


class CompareResponse(BaseModel):
    union_keys: int
    common_keys: int
    a: CompareSide
    b: CompareSide


class MergeRequest(BaseModel):
    """Merge ``source`` ids into ``target`` — never overwrites originals,
    never invents translations."""

    target_id: str = Field(description="File whose text is preserved verbatim")
    source_id: str = Field(description="File contributing the missing ids")
    mode: Literal["placeholder", "fill_from_source"] = Field(
        default="placeholder",
        description="placeholder: add <MISSING> markers; fill_from_source: copy source text verbatim (never translated)",
    )


class MergeResponse(BaseModel):
    download_id: str
    download_url: str = Field(examples=["/api/downloads/8f14e45fceea167a5a36dedd4bea2543"])
    filename: str = Field(examples=["RelicCOH.English.merged.ucs"])
    total_entries: int
    preserved: int = Field(description="Entries kept verbatim from the target")
    added: int = Field(description="Ids added from the source")
    mode: str


class VersionInfo(BaseModel):
    """A known CoH1 UCS localization version in the built-in registry."""

    id: str = Field(examples=["nsv-english"])
    name: str
    origin: str = Field(description="Where this version comes from")
    keys: int
    completeness: str
    notes: str
    available: bool = Field(description="True when the file is present on this server")
    download_url: Optional[str] = None


class VersionListResponse(BaseModel):
    versions: list[VersionInfo]


class ExternalTool(BaseModel):
    """A curated external tool or reference."""

    name: str
    url: str
    category: str
    description: str


class ToolListResponse(BaseModel):
    tools: list[ExternalTool]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    files: int
    versions: int
    service: str


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------- extended
class DiffRowModel(BaseModel):
    key: int
    a_value: Optional[str] = None
    b_value: Optional[str] = None
    kind: str


class DiffPage(BaseModel):
    file_a: str
    file_b: str
    filter: str
    total: int
    offset: int
    limit: int
    rows: list[DiffRowModel]


class RangeHeatmapSegment(BaseModel):
    start: int
    end: int
    count: int
    missing: bool = True


class RangeHeatmapResponse(BaseModel):
    a_id: str
    b_id: str
    a_missing: list[RangeHeatmapSegment]
    b_missing: list[RangeHeatmapSegment]


class LintResponse(BaseModel):
    file_id: str
    total_entries: int
    entries_with_issues: int
    token_issue_count: int
    script_finding_count: int
    summary_only: bool = False


class FingerprintResponse(BaseModel):
    file_id: str
    sha256: str
    size: int
    encoding: str
    has_bom: bool
    bom_hex: str
    crlf_count: int
    lf_only_count: int
    matches_known_nsv: bool


class IssuesResponse(BaseModel):
    file_id: str
    duplicates: list[dict]
    invalid_lines: list[dict]


class LanguageHubCard(BaseModel):
    code: str
    name: str
    source_badge: str
    keys: int
    coverage_percent: float
    reference_keys: int
    download_url: Optional[str] = None
    notes: str = ""


class LanguageHubResponse(BaseModel):
    languages: list[LanguageHubCard]
    reference_id: Optional[str] = None


class MergePreviewRequest(BaseModel):
    target_id: str
    source_id: str
    mode: Literal["placeholder", "fill_from_source"] = "placeholder"
    limit: int = Field(default=50, ge=1, le=500)


class MergePreviewRow(BaseModel):
    key: int
    target_value: Optional[str]
    source_value: Optional[str]
    result_value: str


class MergePreviewResponse(BaseModel):
    total_would_add: int
    preview: list[MergePreviewRow]


class InstallCandidate(BaseModel):
    install_type: str
    base_path: str
    ucs_path: Optional[str]
    exists: bool


class InstallDetectResponse(BaseModel):
    candidates: list[InstallCandidate]
    backup_command: str
    copy_command: str


class MtQueueRequest(BaseModel):
    source_id: str
    sl: str = "ru"
    tl: str = "en"
    limit: Optional[int] = Field(default=20, ge=1, le=500)
    reference_id: Optional[str] = None


class MtStatusResponse(BaseModel):
    status: str
    progress: int = 0
    total: int = 0
    message: str = ""


class GlossaryResponse(BaseModel):
    terms: dict[str, str]


class TimelineEntry(BaseModel):
    id: str
    era: str
    name: str
    keys: int
    size: int
    notes: str
    available: bool


class TimelineResponse(BaseModel):
    entries: list[TimelineEntry]


class DepotCard(BaseModel):
    app_id: int
    depot_id: int
    language: str
    description: str
    command_template: str


class SourceRegistryEntry(BaseModel):
    name: str
    url: str
    trust: str
    description: str


class SearchHit(BaseModel):
    file_id: str
    file_name: str
    key: int
    value: str
    score: Optional[float] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]


class CrossRefVersion(BaseModel):
    file_id: str
    file_name: str
    value: Optional[str]
    similarity: float


class CrossRefResponse(BaseModel):
    key: int
    versions: list[CrossRefVersion]


class BookmarksResponse(BaseModel):
    ids: list[int]


class BatchCompareRequest(BaseModel):
    file_ids: list[str] = Field(min_length=2)


class BatchCompareResponse(BaseModel):
    job_id: str
    pairs: int
    download_url: str


class PatchBuildRequest(BaseModel):
    file_id: str
    ranges: list[str]


class PatchBuildResponse(BaseModel):
    download_id: str
    download_url: str
    keys: int


class SgaFileInfo(BaseModel):
    path: str
    size: int
    likely_stub: bool


class SgaScanResponse(BaseModel):
    install_path: str
    files: list[SgaFileInfo]


class GameProfile(BaseModel):
    id: str
    encoding: str
    notes: str


class AuditEntry(BaseModel):
    ts: float
    action: str
    detail: str
    file_id: str = ""


class AuditResponse(BaseModel):
    entries: list[AuditEntry]
