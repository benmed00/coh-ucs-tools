"""Extended REST API routes (analysis, localization, search, ops)."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from merge import PLACEHOLDER, merge_documents
from parser import serialize, write_file
from statistics import Comparison, compress_ranges
from ucs_analysis import (
    crossref_similarity,
    diff_entries,
    fingerprint_file,
    fuzzy_search,
    lint_document,
    range_heatmap,
    subset_by_ranges,
)

from .deps import KNOWN_VERSIONS, _get_record, _summary, get_store
from .models import (
    AuditResponse,
    BatchCompareRequest,
    BatchCompareResponse,
    BookmarksResponse,
    CrossRefResponse,
    CrossRefVersion,
    DepotCard,
    DiffPage,
    DiffRowModel,
    FingerprintResponse,
    GameProfile,
    GlossaryResponse,
    InstallCandidate,
    InstallDetectResponse,
    InstallCandidate as _IC,
    IssuesResponse,
    LanguageHubCard,
    LanguageHubResponse,
    LintResponse,
    MergePreviewRequest,
    MergePreviewResponse,
    MergePreviewRow,
    MtQueueRequest,
    MtStatusResponse,
    PatchBuildRequest,
    PatchBuildResponse,
    RangeHeatmapResponse,
    RangeHeatmapSegment,
    SearchHit,
    SearchResponse,
    SearchHit as _SH,
    SourceRegistryEntry,
    TimelineEntry,
    TimelineResponse,
    SgaFileInfo,
    SgaScanResponse,
)
from . import services

logger = logging.getLogger(__name__)

ext_router = APIRouter()

# Install path templates (read-only scan)
INSTALL_PATHS = [
    ("THQ retail", Path(r"c:\Program Files (x86)\THQ\Company of Heroes"),
     "Engine/Locale/English/RelicCOH.English.ucs"),
    ("Steam CoH", Path(r"c:\Program Files (x86)\Steam\steamapps\common\Company of Heroes"),
     "Engine/Locale/English/RelicCOH.English.ucs"),
    ("Complete Edition", Path(r"c:\Games\Company of Heroes - Complete Edition\CoH"),
     "Engine/Locale/Russian/RelicCOH.Russian.ucs"),
    ("Complete Edition EN", Path(r"c:\Games\Company of Heroes - Complete Edition\CoH"),
     "Engine/Locale/English/RelicCOH.English.ucs"),
]

TIMELINE_ORDER = [
    ("thq-retail-english", "THQ retail (2006)"),
    ("nsv-english", "New Steam Version"),
    ("ce-russian", "Complete Edition"),
    ("complete-english", "Union build"),
]

COMMUNITY_SOURCES = [
    {"name": "vscode-relic-ucs", "url": "https://github.com/Janne252/vscode-relic-ucs",
     "trust": "high", "description": "VS Code syntax highlighting for Relic UCS files."},
    {"name": "Steam NSV English thread", "url": "https://steamcommunity.com/app/228200/discussions/0/353915847943232144/",
     "trust": "official-community", "description": "Community thread sharing the official NSV English UCS."},
    {"name": "GameSaveInfo — CoH", "url": "https://www.gamesave.info/game/company-of-heroes/",
     "trust": "reference", "description": "Documented install paths for CoH editions."},
]

DEPOT_CARDS = [
    {"app_id": 4560, "depot_id": 4565, "language": "French",
     "description": "Legacy CoH French locale depot",
     "command_template": "DepotDownloader -app 4560 -depot 4565 -lang french"},
    {"app_id": 228200, "depot_id": 228201, "language": "English",
     "description": "New Steam Version English depot",
     "command_template": "DepotDownloader -app 228200 -depot 228201 -lang english"},
]

SGA_PLUGIN_TOOLS = [
    {"name": "Corsix Mod Studio", "url": "https://modstudio.corsix.org/",
     "category": "SGA / modding", "description": "Open and edit Relic SGA archives."},
    {"name": "SGA Reader (community)", "url": "https://github.com/search?q=relic+sga",
     "category": "SGA tools", "description": "Community tools for extracting Relic archive formats."},
]

GAME_PROFILES = [
    {"id": "coh1", "encoding": "utf-16-le", "notes": "BOM FF FE, CRLF, id<TAB>text. Engine fallback: $id No Key."},
    {"id": "coh2", "encoding": "utf-16-le", "notes": "Similar to CoH1; key ranges differ. Stub profile — verify before use."},
    {"id": "dow1", "encoding": "utf-16-le", "notes": "Dawn of War UCS dialect; different id namespaces."},
]


# ------------------------------------------------------------------ diff
@ext_router.get("/files/{file_id}/diff/{other_id}", tags=["analysis"], response_model=DiffPage,
                summary="Entry-level diff between two files")
def file_diff(
    request: Request,
    file_id: str,
    other_id: str,
    filter: str = Query("changed", pattern="^(changed|missing|empty|token_mismatch)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> DiffPage:
    store = get_store(request)
    _get_record(store, file_id)
    _get_record(store, other_id)
    rows = diff_entries(store.document(file_id), store.document(other_id), filter)
    window = rows[offset:offset + limit]
    return DiffPage(
        file_a=file_id, file_b=other_id, filter=filter, total=len(rows),
        offset=offset, limit=limit,
        rows=[DiffRowModel(key=r.key, a_value=r.a_value, b_value=r.b_value, kind=r.kind)
              for r in window],
    )


@ext_router.get("/compare/{a}/{b}/ranges", tags=["analysis"], response_model=RangeHeatmapResponse,
                summary="Missing-id heatmap buckets for two files")
def compare_ranges(request: Request, a: str, b: str,
                   bucket_size: int = Query(1000, ge=100, le=50000)) -> RangeHeatmapResponse:
    store = get_store(request)
    _get_record(store, a)
    _get_record(store, b)
    comp = Comparison(russian=store.document(a), english=store.document(b))
    return RangeHeatmapResponse(
        a_id=a, b_id=b,
        a_missing=[RangeHeatmapSegment(**s) for s in range_heatmap(comp.missing_in_russian, bucket_size=bucket_size)],
        b_missing=[RangeHeatmapSegment(**s) for s in range_heatmap(comp.missing_in_english, bucket_size=bucket_size)],
    )


@ext_router.get("/files/{file_id}/lint", tags=["analysis"], response_model=LintResponse,
                summary="Format-token and script lint")
def lint_file(request: Request, file_id: str,
              summary_only: bool = Query(False)) -> LintResponse:
    store = get_store(request)
    _get_record(store, file_id)
    result = lint_document(store.document(file_id))
    return LintResponse(
        file_id=file_id,
        total_entries=result["total_entries"],
        entries_with_issues=result["entries_with_issues"],
        token_issue_count=result["token_issue_count"],
        script_finding_count=result["script_finding_count"],
        summary_only=summary_only,
    )


@ext_router.get("/files/{file_id}/issues", tags=["analysis"], response_model=IssuesResponse,
                summary="Duplicates and invalid lines")
def file_issues(request: Request, file_id: str) -> IssuesResponse:
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    dups = [{"key": k, "lines": lines} for k, lines in sorted(doc.duplicates.items())]
    invalid = [{"line": ln.line_number, "reason": ln.reason, "raw": ln.raw[:200]}
               for ln in doc.invalid_lines]
    return IssuesResponse(file_id=file_id, duplicates=dups, invalid_lines=invalid)


@ext_router.get("/files/{file_id}/issues.csv", tags=["analysis"], response_class=PlainTextResponse,
                summary="Export issues as CSV")
def file_issues_csv(request: Request, file_id: str) -> PlainTextResponse:
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["type", "key", "line", "detail"])
    for k, lines in sorted(doc.duplicates.items()):
        w.writerow(["duplicate", k, ",".join(map(str, lines)), ""])
    for ln in doc.invalid_lines:
        w.writerow(["invalid", "", ln.line_number, f"{ln.reason}: {ln.raw[:120]}"])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                               headers={"Content-Disposition": f'attachment; filename="{file_id}-issues.csv"'})


@ext_router.get("/files/{file_id}/fingerprint", tags=["analysis"], response_model=FingerprintResponse,
                summary="File fingerprint (sha256, BOM, encoding)")
def file_fingerprint(request: Request, file_id: str) -> FingerprintResponse:
    store = get_store(request)
    rec = _get_record(store, file_id)
    fp = fingerprint_file(Path(rec.stored_path))
    return FingerprintResponse(file_id=file_id, **fp.__dict__)


# ----------------------------------------------------------- localization
def _reference_keys(store) -> tuple[int, Optional[str]]:
    for vid in ("complete-english", "nsv-english", "ce-russian"):
        rec = store.get(vid)
        if rec and rec.keys:
            return rec.keys, vid
    return 0, None


@ext_router.get("/languages", tags=["versions"], response_model=LanguageHubResponse,
                summary="Localization hub cards")
def language_hub(request: Request) -> LanguageHubResponse:
    store = get_store(request)
    ref_keys, ref_id = _reference_keys(store)

    def card(code: str, name: str, badge: str, version_id: str, notes: str) -> LanguageHubCard:
        rec = store.get(version_id)
        keys = rec.keys if rec else 0
        cov = round(100.0 * keys / ref_keys, 2) if ref_keys and keys else 0.0
        dl = f"/api/downloads/{version_id}" if rec else None
        # Also check repo-local MT/build files
        if not rec and code == "AR":
            ar = Path("RelicCOH.Arabic.MT.ucs")
            if ar.exists():
                from parser import parse_file
                doc = parse_file(ar)
                keys = len(doc.entries)
                cov = round(100.0 * keys / ref_keys, 2) if ref_keys else 0.0
        return LanguageHubCard(
            code=code, name=name, source_badge=badge, keys=keys,
            coverage_percent=cov, reference_keys=ref_keys,
            download_url=dl, notes=notes,
        )

    langs = [
        card("EN", "English", "official/complete", "complete-english",
             "NSV official + legacy THQ keys union."),
        card("FR", "French", "depot/needs file", "thq-retail-english",
             "French depot 4565 — use DepotDownloader; no built-in FR UCS yet."),
        card("AR", "Arabic", "MT (unofficial)", "nsv-english",
             "Machine-translated build for QA — not for official deliverables."),
        card("RU", "Russian", "CE reference", "ce-russian",
             "Complete Edition Russian — usual id-set reference."),
    ]
    return LanguageHubResponse(languages=langs, reference_id=ref_id)


@ext_router.post("/merge/preview", tags=["merge"], response_model=MergePreviewResponse,
                 summary="Preview first N merge changes without writing")
def merge_preview(request: Request, req: MergePreviewRequest) -> MergePreviewResponse:
    store = get_store(request)
    _get_record(store, req.target_id)
    _get_record(store, req.source_id)
    target = store.document(req.target_id)
    source = store.document(req.source_id)
    fill = req.mode == "fill_from_source"
    preview: list[MergePreviewRow] = []
    for key in sorted(source.entries.keys() - target.entries.keys()):
        src_val = source.entries[key]
        res_val = src_val if fill else PLACEHOLDER
        preview.append(MergePreviewRow(
            key=key, target_value=None, source_value=src_val, result_value=res_val,
        ))
        if len(preview) >= req.limit:
            break
    total = len(source.entries.keys() - target.entries.keys())
    return MergePreviewResponse(total_would_add=total, preview=preview)


@ext_router.get("/install/detect", tags=["tools"], response_model=InstallDetectResponse,
                summary="Scan known CoH install paths (read-only)")
def install_detect() -> InstallDetectResponse:
    candidates: list[InstallCandidate] = []
    ucs_found: Optional[Path] = None
    for label, base, rel in INSTALL_PATHS:
        ucs = base / rel
        exists = ucs.exists()
        candidates.append(InstallCandidate(
            install_type=label, base_path=str(base),
            ucs_path=str(ucs) if exists else None, exists=exists,
        ))
        if exists and ucs_found is None:
            ucs_found = ucs
    ucs_str = str(ucs_found) if ucs_found else "C:\\Path\\To\\RelicCOH.English.ucs"
    backup = f'Copy-Item "{ucs_str}" "{ucs_str}.backup" -Force'
    copy = f'Copy-Item ".\\RelicCOH.English.complete.ucs" "{ucs_str}" -Force'
    return InstallDetectResponse(candidates=candidates, backup_command=backup, copy_command=copy)


@ext_router.post("/mt/queue", tags=["analysis"], summary="Queue MT comparison job")
def mt_queue(request: Request, req: MtQueueRequest) -> dict:
    store = get_store(request)
    rec = _get_record(store, req.source_id)
    ref_path = None
    if req.reference_id:
        ref_rec = _get_record(store, req.reference_id)
        ref_path = Path(ref_rec.stored_path)
    result = services.queue_mt_job(
        source_path=Path(rec.stored_path), reference_path=ref_path,
        sl=req.sl, tl=req.tl, limit=req.limit,
    )
    services.audit_log("mt_queue", f"{req.sl}->{req.tl} limit={req.limit}", file_id=req.source_id)
    return result


@ext_router.get("/mt/status", tags=["analysis"], response_model=MtStatusResponse,
                summary="MT job status")
def mt_status_endpoint() -> MtStatusResponse:
    s = services.mt_status()
    return MtStatusResponse(**{k: s.get(k, "" if k == "message" else 0) for k in ("status", "progress", "total", "message")})


@ext_router.get("/mt/report", tags=["analysis"], summary="MT comparison report JSON")
def mt_report_endpoint() -> dict:
    return services.mt_report()


@ext_router.get("/glossary", tags=["tools"], response_model=GlossaryResponse,
                summary="Get MT post-processing glossary")
def get_glossary() -> GlossaryResponse:
    return GlossaryResponse(terms=services.get_glossary())


@ext_router.put("/glossary", tags=["tools"], response_model=GlossaryResponse,
                summary="Replace glossary terms")
def put_glossary(body: GlossaryResponse) -> GlossaryResponse:
    services.put_glossary(body.terms)
    services.audit_log("glossary_update", f"{len(body.terms)} terms")
    return GlossaryResponse(terms=services.get_glossary())


# --------------------------------------------------------- versions/meta
@ext_router.get("/versions/timeline", tags=["versions"], response_model=TimelineResponse,
                summary="Version history timeline")
def versions_timeline(request: Request) -> TimelineResponse:
    store = get_store(request)
    entries = []
    for vid, era in TIMELINE_ORDER:
        meta = next((m for m in KNOWN_VERSIONS if m["id"] == vid), None)
        rec = store.get(vid)
        entries.append(TimelineEntry(
            id=vid, era=era,
            name=meta["name"] if meta else vid,
            keys=rec.keys if rec else 0,
            size=rec.size if rec else 0,
            notes=meta["notes"] if meta else "",
            available=rec is not None,
        ))
    return TimelineResponse(entries=entries)


@ext_router.get("/depots", tags=["tools"], summary="Steam depot cards")
def list_depots() -> dict:
    return {"depots": DEPOT_CARDS}


@ext_router.get("/sources", tags=["tools"], summary="Community source registry")
def list_sources() -> dict:
    return {"sources": COMMUNITY_SOURCES}


# ---------------------------------------------------------------- search
@ext_router.get("/search/global", tags=["analysis"], response_model=SearchResponse,
                summary="Cross-version search")
def global_search(
    request: Request,
    q: str = Query(min_length=1),
    regex: bool = Query(False),
    fuzzy: bool = Query(False),
    file_ids: Optional[str] = Query(None, description="Comma-separated file ids"),
    limit: int = Query(50, ge=1, le=200),
) -> SearchResponse:
    import re as re_mod
    store = get_store(request)
    ids = [s.strip() for s in (file_ids or "").split(",") if s.strip()]
    if not ids:
        ids = [r.id for r in store.list()]
    hits: list[SearchHit] = []
    for fid in ids:
        rec = store.get(fid)
        if not rec:
            continue
        doc = store.document(fid)
        if fuzzy:
            for key, value, score in fuzzy_search(q, doc.entries, limit=limit):
                hits.append(SearchHit(file_id=fid, file_name=rec.name, key=key, value=value, score=score))
        elif regex:
            try:
                pat = re_mod.compile(q, re_mod.IGNORECASE)
            except re_mod.error as exc:
                raise HTTPException(400, f"Invalid regex: {exc}") from exc
            for key, value in doc.sorted_entries():
                if pat.search(value) or pat.search(str(key)):
                    hits.append(SearchHit(file_id=fid, file_name=rec.name, key=key, value=value))
        else:
            needle = q.lower()
            for key, value in doc.sorted_entries():
                if needle in value.lower() or needle in str(key):
                    hits.append(SearchHit(file_id=fid, file_name=rec.name, key=key, value=value))
        if len(hits) >= limit:
            break
    hits = hits[:limit]
    return SearchResponse(query=q, total=len(hits), hits=hits)


@ext_router.get("/crossref/{key}", tags=["analysis"], response_model=CrossRefResponse,
                summary="Cross-reference one entry id across all stored files")
def crossref_key(request: Request, key: int) -> CrossRefResponse:
    store = get_store(request)
    files = store.list()
    if not files:
        raise HTTPException(404, "No files stored")
    base_rec = files[0]
    base_doc = store.document(base_rec.id)
    base_val = base_doc.entries.get(key, "")
    versions: list[CrossRefVersion] = []
    for rec in store.list():
        doc = store.document(rec.id)
        val = doc.entries.get(key)
        sim = crossref_similarity(base_val, val or "") if base_val or val else 0.0
        versions.append(CrossRefVersion(
            file_id=rec.id, file_name=rec.name, value=val, similarity=sim,
        ))
    return CrossRefResponse(key=key, versions=versions)


@ext_router.get("/bookmarks", tags=["tools"], response_model=BookmarksResponse,
                summary="List bookmarked entry ids")
def get_bookmarks() -> BookmarksResponse:
    return BookmarksResponse(ids=services.get_bookmarks())


@ext_router.post("/bookmarks", tags=["tools"], response_model=BookmarksResponse,
                 summary="Add bookmark id(s)")
def post_bookmarks(body: BookmarksResponse) -> BookmarksResponse:
    ids = services.get_bookmarks()
    for k in body.ids:
        if k not in ids:
            ids.append(k)
    return BookmarksResponse(ids=services.set_bookmarks(ids))


@ext_router.delete("/bookmarks/{key}", tags=["tools"], response_model=BookmarksResponse,
                   summary="Remove bookmark id")
def delete_bookmark(key: int) -> BookmarksResponse:
    return BookmarksResponse(ids=services.remove_bookmark(key))


# ---------------------------------------------------------------- batch
@ext_router.post("/batch/compare", tags=["analysis"], response_model=BatchCompareResponse,
                 summary="Compare all pairs of files")
def batch_compare(request: Request, req: BatchCompareRequest) -> BatchCompareResponse:
    store = get_store(request)
    for fid in req.file_ids:
        _get_record(store, fid)
    job = services.run_batch_compare(req.file_ids, store)
    return BatchCompareResponse(
        job_id=job.id, pairs=len(job.pairs),
        download_url=f"/api/batch/compare/{job.id}/zip",
    )


@ext_router.get("/batch/compare/{job_id}/zip", tags=["analysis"], response_class=FileResponse,
                summary="Download batch compare zip")
def batch_compare_zip(job_id: str) -> FileResponse:
    path = services.batch_zip_path(job_id)
    if not path:
        raise HTTPException(404, f"No batch job {job_id!r}")
    return FileResponse(path, filename=f"batch-{job_id}.zip", media_type="application/zip")


@ext_router.get("/export/openapi-client", tags=["tools"], summary="API usage snippets")
def openapi_client_snippets(request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    return {
        "curl_upload": f'curl -F "file=@RelicCOH.English.ucs" {base}/api/files',
        "curl_compare": f'curl "{base}/api/compare?a=FILE_A&b=FILE_B"',
        "python_example": (
            "import httpx\n"
            f'BASE = "{base}"\n'
            "with open('file.ucs', 'rb') as f:\n"
            "    r = httpx.post(f'{BASE}/api/files', files={'file': f})\n"
            "    file_id = r.json()['file']['id']\n"
            "print(httpx.get(f'{BASE}/api/files/{file_id}/validate').json())"
        ),
    }


# -------------------------------------------------------------- advanced
@ext_router.get("/sga/scan", tags=["tools"], response_model=SgaScanResponse,
                summary="List .sga archives under install path")
def sga_scan(install_path: str = Query(...)) -> SgaScanResponse:
    base = Path(install_path)
    if not base.exists():
        raise HTTPException(404, f"Path not found: {install_path}")
    files: list[SgaFileInfo] = []
    for pattern in ("WW2/Archives/**/*.sga", "Engine/Archives/**/*.sga", "**/*.sga"):
        for p in base.glob(pattern):
            if p.is_file():
                size = p.stat().st_size
                files.append(SgaFileInfo(
                    path=str(p.relative_to(base)), size=size,
                    likely_stub=size < 10_240,
                ))
    # dedupe by path
    seen = set()
    unique = []
    for f in sorted(files, key=lambda x: x.path):
        if f.path not in seen:
            seen.add(f.path)
            unique.append(f)
    return SgaScanResponse(install_path=str(base), files=unique)


@ext_router.get("/games", tags=["tools"], summary="Game variant profiles")
def game_profiles() -> dict:
    return {"profiles": GAME_PROFILES}


@ext_router.post("/patch/build", tags=["merge"], response_model=PatchBuildResponse,
                 summary="Build subset UCS from ranges")
def patch_build(request: Request, req: PatchBuildRequest) -> PatchBuildResponse:
    store = get_store(request)
    rec = _get_record(store, req.file_id)
    doc = store.document(req.file_id)
    subset = subset_by_ranges(doc.entries, req.ranges)
    if not subset:
        raise HTTPException(400, "No entries matched the given ranges")
    out_path = store.generated_dir / f"patch-{uuid.uuid4().hex}.ucs"
    write_file(out_path, sorted(subset.items()), overwrite=True)
    gen = store.add_generated(out_path, f"{rec.name.split('.')[0]}.patch.ucs")
    services.audit_log("patch_build", f"{len(subset)} keys", file_id=req.file_id)
    return PatchBuildResponse(
        download_id=gen.id, download_url=f"/api/downloads/{gen.id}", keys=len(subset),
    )


@ext_router.get("/audit", tags=["meta"], response_model=AuditResponse,
                summary="Recent operations audit log")
def get_audit_log(limit: int = Query(50, ge=1, le=200)) -> AuditResponse:
    from .models import AuditEntry
    entries = [AuditEntry(**e) for e in services.get_audit(limit)]
    return AuditResponse(entries=entries)
