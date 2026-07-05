"""REST API routes.

Every endpoint delegates to the existing CLI toolkit modules
(:mod:`parser`, :mod:`validator`, :mod:`statistics`, :mod:`merge`) —
no parsing/validation/merge logic is reimplemented here.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from merge import merge_and_write
from game_profiles import classify_document, validate_against_profile
from ucs_stats import Comparison, compress_ranges
from validator import validate

from .models import (CompareResponse, CompareSide, EntriesPage, Entry,
                     ErrorResponse, ExternalTool, FileListResponse,
                     FileSummary, HealthResponse, MergeRequest, MergeResponse,
                     ToolListResponse, UploadResponse, ValidationIssue,
                     ValidationResponse, VersionInfo, VersionListResponse)
from . import services
from .routes_extended import ext_router
from .auth_routes import auth_router
from .store import MAX_UPLOAD_BYTES, FileStore, StoredFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

from .deps import (
    EXTERNAL_TOOLS, KNOWN_VERSIONS, SGA_PLUGIN_TOOLS,
    _get_record, _summary, get_store, raise_profile_strict,
)


# ------------------------------------------------------------------- files
@router.post("/files", tags=["files"], response_model=UploadResponse, status_code=201,
             responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
             summary="Upload and analyze a .ucs file")
async def upload_file(
    request: Request,
    file: UploadFile,
    game_profile: str = Query("coh1", pattern="^(coh1|coh2|dow1|dow2)$"),
    strict_profile: bool = Query(False, description="Reject upload when classification does not match game_profile"),
) -> UploadResponse:
    """Upload a UCS localization file (multipart). The file is parsed
    immediately: encoding and BOM are auto-detected, duplicates and invalid
    lines are counted, and a summary is returned along with the new file id.
    Maximum size: 20 MB."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 20 MB upload limit")
    if not raw:
        raise HTTPException(400, "Uploaded file is empty")
    store = get_store(request)
    rec = store.add_upload(file.filename or "upload.ucs", raw)
    doc = store.document(rec.id)
    classification = classify_document(doc)
    profile_check = validate_against_profile(doc, game_profile)
    if strict_profile and classification["best_match"] != game_profile:
        store.delete(rec.id)
        raise HTTPException(
            422,
            detail={
                "message": f"File does not match profile {game_profile!r}",
                "best_match": classification["best_match"],
                "confidence": classification["confidence"],
            },
        )
    services.audit_log("upload", rec.name, file_id=rec.id)
    return UploadResponse(
        file=_summary(rec),
        message=f"Parsed {rec.keys} entries",
        game_profile=classification,
        profile_check=profile_check,
    )


@router.get("/files", tags=["files"], response_model=FileListResponse,
            summary="List stored files")
def list_files(request: Request) -> FileListResponse:
    """All files known to the server: uploads, built-in versions and
    generated merge results."""
    return FileListResponse(files=[_summary(r) for r in get_store(request).list()])


@router.get("/files/{file_id}", tags=["files"], response_model=FileSummary,
            responses={404: {"model": ErrorResponse}}, summary="File summary")
def get_file(request: Request, file_id: str) -> FileSummary:
    return _summary(_get_record(get_store(request), file_id))


@router.delete("/files/{file_id}", tags=["files"], status_code=204,
               responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
               summary="Delete an uploaded or generated file")
def delete_file(request: Request, file_id: str) -> None:
    """Built-in versions are read-only and refuse deletion (403)."""
    store = get_store(request)
    _get_record(store, file_id)
    try:
        store.delete(file_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/files/{file_id}/entries", tags=["files"], response_model=EntriesPage,
            responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
            summary="Browse / search entries")
def list_entries(
    request: Request,
    file_id: str,
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    search: str | None = Query(None, description="Filter by id or text"),
    regex: bool = Query(False, description="Treat `search` as a regular expression"),
) -> EntriesPage:
    """Paginated entries, numerically sorted. `search` matches the numeric id
    (as a string) or the value text; case-insensitive substring by default,
    full regular expression when `regex=true`."""
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    pairs = doc.sorted_entries()

    if search:
        if regex:
            try:
                pattern = re.compile(search, re.IGNORECASE)
            except re.error as exc:
                raise HTTPException(400, f"Invalid regex: {exc}") from exc
            pairs = [(k, v) for k, v in pairs if pattern.search(v) or pattern.search(str(k))]
        else:
            needle = search.lower()
            pairs = [(k, v) for k, v in pairs if needle in v.lower() or needle in str(k)]

    total = len(pairs)
    window = pairs[offset:offset + limit]
    return EntriesPage(
        file_id=file_id, total=total, offset=offset, limit=limit,
        search=search, regex=regex,
        entries=[Entry(key=k, value=v) for k, v in window],
    )


@router.get("/files/{file_id}/validate", tags=["analysis"], response_model=ValidationResponse,
            responses={404: {"model": ErrorResponse}}, summary="Validate a file")
def validate_file(request: Request, file_id: str) -> ValidationResponse:
    """Run the full validator: duplicate ids, invalid lines, empty values,
    bad characters (lone surrogates / control chars), strict UTF-16 round-trip."""
    store = get_store(request)
    _get_record(store, file_id)
    result = validate(store.document(file_id))
    return ValidationResponse(
        file_id=file_id, ok=result.ok,
        errors=len(result.errors), warnings=len(result.warnings),
        issues=[ValidationIssue(severity=i.severity.value, code=i.code,
                                key=i.key, message=i.message)
                for i in result.issues],
    )


# ----------------------------------------------------------------- compare
@router.get("/compare", tags=["analysis"], response_model=CompareResponse,
            responses={404: {"model": ErrorResponse}}, summary="Compare two files")
def compare_files(
    request: Request,
    a: str = Query(description="File id of side A"),
    b: str = Query(description="File id of side B"),
    game_profile: str = Query("coh1", pattern="^(coh1|coh2|dow1|dow2)$"),
    strict_profile: bool = Query(False, description="Reject when either file's classification mismatches game_profile"),
) -> CompareResponse:
    """Coverage statistics for two files plus the missing-id sets of both
    sides compressed into ranges (e.g. `559200-559650`)."""
    store = get_store(request)
    _get_record(store, a)
    _get_record(store, b)
    raise_profile_strict(store, [a, b], game_profile, strict_profile)
    rec_a, rec_b = _get_record(store, a), _get_record(store, b)
    comp = Comparison(russian=store.document(a), english=store.document(b))
    stats = comp.statistics()

    def side(rec: StoredFile, side_stats: dict, missing: list[int]) -> CompareSide:
        return CompareSide(
            id=rec.id, name=rec.name,
            total_keys=side_stats["total_keys"],
            duplicated_keys=side_stats["duplicated_keys"],
            invalid_lines=side_stats["invalid_lines"],
            empty_values=side_stats["empty_values"],
            missing_keys=side_stats["missing_keys"],
            coverage_percent=side_stats["coverage_percent"],
            missing_ranges=compress_ranges(missing),
        )

    # Comparison labels its sides russian/english; here they are simply A/B.
    return CompareResponse(
        union_keys=stats["union_keys"],
        common_keys=stats["common_keys"],
        a=side(rec_a, stats["russian"], comp.missing_in_russian),
        b=side(rec_b, stats["english"], comp.missing_in_english),
    )


# ------------------------------------------------------------------- merge
@router.post("/merge", tags=["merge"], response_model=MergeResponse,
             responses={404: {"model": ErrorResponse}}, summary="Merge two files")
def merge_files(
    request: Request,
    req: MergeRequest,
    game_profile: str = Query("coh1", pattern="^(coh1|coh2|dow1|dow2)$"),
    strict_profile: bool = Query(False, description="Reject when either file's classification mismatches game_profile"),
) -> MergeResponse:
    """Merge `source` ids into `target`. Target text is always preserved
    verbatim; ids that only exist in the source are added either as
    `<MISSING>` placeholders or with the source text copied verbatim
    (`fill_from_source`). **No translation is ever generated.** The result is
    a new file offered for download — originals are never overwritten."""
    store = get_store(request)
    _get_record(store, req.target_id)
    _get_record(store, req.source_id)
    raise_profile_strict(store, [req.target_id, req.source_id], game_profile, strict_profile)
    target_rec = _get_record(store, req.target_id)
    target = store.document(req.target_id)
    source = store.document(req.source_id)

    out_path = store.generated_dir / f"{uuid.uuid4().hex}.ucs"
    result = merge_and_write(target, source, out_path,
                             fill_from_source=(req.mode == "fill_from_source"))

    base = target_rec.name.split(" (")[0]  # drop display suffixes like " (THQ retail)"
    if base.lower().endswith(".ucs"):
        base = base[:-4]
    download_name = f"{base}.merged.ucs"
    rec = store.add_generated(out_path, download_name)
    logger.info("Merged %s + %s -> %s (%d entries, %d added)",
                req.target_id, req.source_id, rec.id,
                len(result.entries), len(result.added_placeholders))
    services.audit_log("merge", f"{req.mode} +{len(result.added_placeholders)}", file_id=rec.id)
    services.fire_webhooks("merge_complete", {
        "file_id": rec.id,
        "keys": len(result.entries),
        "added": len(result.added_placeholders),
        "mode": req.mode,
    })
    return MergeResponse(
        download_id=rec.id,
        download_url=f"/api/downloads/{rec.id}",
        filename=download_name,
        total_entries=len(result.entries),
        preserved=result.preserved,
        added=len(result.added_placeholders),
        mode=req.mode,
    )


@router.get("/downloads/{file_id}", tags=["merge"], response_class=FileResponse,
            responses={404: {"model": ErrorResponse}}, summary="Download a stored file")
def download_file(request: Request, file_id: str) -> FileResponse:
    """Stream any stored file (upload, version copy or merge result) with a
    proper content-disposition filename."""
    rec = _get_record(get_store(request), file_id)
    return FileResponse(rec.stored_path, filename=rec.name,
                        media_type="application/octet-stream")


# ---------------------------------------------------------------- versions
@router.get("/versions", tags=["versions"], response_model=VersionListResponse,
            summary="Known CoH1 UCS versions")
def list_versions(request: Request) -> VersionListResponse:
    """The built-in registry of known Company of Heroes 1 localization
    versions. Versions found on this machine at startup are available for
    analysis and download (served from read-only server-side copies)."""
    store = get_store(request)
    versions = []
    for meta in KNOWN_VERSIONS:
        rec = store.get(meta["id"])
        available = rec is not None
        versions.append(VersionInfo(
            id=meta["id"], name=meta["name"], origin=meta["origin"],
            keys=rec.keys if rec else 0,
            completeness=meta["completeness"], notes=meta["notes"],
            available=available,
            download_url=f"/api/versions/{meta['id']}/download" if available else None,
        ))
    return VersionListResponse(versions=versions)


@router.get("/versions/{version_id}/download", tags=["versions"], response_class=FileResponse,
            responses={404: {"model": ErrorResponse}}, summary="Download a registered version")
def download_version(request: Request, version_id: str) -> FileResponse:
    rec = get_store(request).get(version_id)
    if rec is None or rec.kind != "version":
        raise HTTPException(404, f"No registered version with id {version_id!r}")
    filename = rec.name.split(" ")[0]  # "RelicCOH.English.ucs (THQ retail)" -> file part
    return FileResponse(rec.stored_path, filename=filename,
                        media_type="application/octet-stream")


# ------------------------------------------------------------------- misc
@router.get("/tools", tags=["tools"], response_model=ToolListResponse,
            summary="Curated external tools & references")
def list_tools() -> ToolListResponse:
    """External tools, depot references and community resources relevant to
    CoH1 UCS localization work."""
    tools = [ExternalTool(**t) for t in EXTERNAL_TOOLS]
    tools.extend(ExternalTool(**t) for t in SGA_PLUGIN_TOOLS)
    return ToolListResponse(tools=tools)


router.include_router(auth_router)
router.include_router(ext_router)


@router.get("/health", tags=["meta"], response_model=HealthResponse, summary="Health check")
def health(request: Request) -> HealthResponse:
    store = get_store(request)
    return HealthResponse(status="ok", files=len(store.list()),
                          versions=len(store.list("version")),
                          service="coh-ucs-tools")
