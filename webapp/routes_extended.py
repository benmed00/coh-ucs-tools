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

from depot_downloader import (
    DEPOT_SPECS,
    DOWNLOADS_DIR,
    download_depot_locale,
    find_depotdownloader,
    list_depot_specs,
    run_locale_build,
)
from locale_coverage import build_coverage_table, coverage_to_csv, write_coverage_report
from game_profiles import classify_document, list_profiles as game_profile_list, validate_against_profile
from merge import PLACEHOLDER, merge_documents, merge_threeway_and_write
from po_io import export_po, export_tmx, import_po, import_tmx
from patch_chain import build_patch_chain
from sga_reader import (
    extract_file,
    extract_all_locale_ucs,
    find_locale_ucs,
    inject_ucs_into_sga,
    list_sga_contents,
    pack_sga,
    read_sga,
    repack_sga,
    scan_install_locale_archives,
)
from ucs_analysis import campaign_ranges, voice_crosslink
from parser import serialize, write_file
from ucs_stats import Comparison, compress_ranges
from ucs_analysis import (
    crossref_similarity,
    diff_entries,
    fingerprint_file,
    fuzzy_search,
    lint_document,
    range_heatmap,
    subset_by_ranges,
    apply_patch_overlay,
    export_unified_diff,
)

from .deps import KNOWN_VERSIONS, _get_record, _summary, get_store, raise_profile_strict
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
    LocaleCoverageResponse,
    LocaleCoverageRowModel,
    LintResponse,
    MergePreviewRequest,
    MergePreviewResponse,
    MergePreviewRow,
    MtQueueRequest,
    MtStatusResponse,
    PatchBuildRequest,
    PatchBuildResponse,
    PatchApplyRequest,
    PatchApplyResponse,
    PatchChainResponse,
    PatchChainStep,
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
from verification_checklist import run_checklist

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
    {
        "app_id": s["app_id"],
        "depot_id": s["depot_id"],
        "language": s["language"].title(),
        "description": f"CoH {s['language']} locale depot (app {s['app_id']}, depot {s['depot_id']})",
        "command_template": s["command_template"],
        "expected_file": s["expected_file"],
        "build_script": s.get("build_script"),
        "depot_verified": s.get("depot_verified", False),
        "steamdb_note": s.get("steamdb_note"),
    }
    for s in list_depot_specs()
]

SGA_PLUGIN_TOOLS = [
    {"name": "Corsix Mod Studio", "url": "https://modstudio.corsix.org/",
     "category": "SGA / modding", "description": "Open and edit Relic SGA archives."},
    {"name": "SGA Reader (community)", "url": "https://github.com/search?q=relic+sga",
     "category": "SGA tools", "description": "Community tools for extracting Relic archive formats."},
]

GAME_PROFILES = game_profile_list()


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

    def locale_file_card(
        code: str, name: str, version_id: str, filename: str, depot: str, notes: str,
    ) -> LanguageHubCard:
        rec = store.get(version_id)
        keys = rec.keys if rec else 0
        badge = f"needs file (depot {depot})"
        note = f"{notes} Run build_{name.lower()}.py after recovering NSV UCS."
        if not rec:
            path = Path(filename)
            if path.is_file():
                from parser import parse_file
                doc = parse_file(path)
                keys = len(doc.entries)
                badge = "built/complete (disk)"
        else:
            badge = "built/complete"
            note = notes
        cov = round(100.0 * keys / ref_keys, 2) if ref_keys and keys else 0.0
        dl = f"/api/downloads/{version_id}" if rec else None
        return LanguageHubCard(
            code=code, name=name, source_badge=badge, keys=keys,
            coverage_percent=cov, reference_keys=ref_keys,
            download_url=dl, notes=note,
        )

    langs = [
        card("EN", "English", "official/complete", "complete-english",
             "NSV official + legacy THQ keys union."),
        locale_file_card("FR", "French", "french-complete", "RelicCOH.French.complete.ucs", "4565",
                         "Official French NSV union build."),
        locale_file_card("DE", "German", "german-complete", "RelicCOH.German.complete.ucs", "4564",
                         "Official German NSV union build."),
        locale_file_card("ES", "Spanish", "spanish-complete", "RelicCOH.Spanish.complete.ucs", "4566",
                         "Official Spanish NSV union build."),
        locale_file_card("IT", "Italian", "italian-complete", "RelicCOH.Italian.complete.ucs", "4567",
                         "Official Italian NSV union build."),
        locale_file_card("PL", "Polish", "polish-complete", "RelicCOH.Polish.complete.ucs", "4568",
                         "Official Polish NSV union build."),
        card("AR", "Arabic", "MT (unofficial)", "arabic-mt",
             "Machine-translated build for QA — not for official deliverables."),
        card("RU", "Russian", "CE reference", "ce-russian",
             "Complete Edition Russian — usual id-set reference."),
    ]
    return LanguageHubResponse(languages=langs, reference_id=ref_id)


@ext_router.get("/languages/coverage", tags=["versions"], response_model=LocaleCoverageResponse,
                summary="Per-locale coverage table vs Russian CE reference")
def languages_coverage(
    request: Request,
    reference_id: str = Query("ce-russian", description="Registered version id for reference UCS"),
) -> LocaleCoverageResponse:
    store = get_store(request)
    ref_rec = store.get(reference_id)
    ref_path = Path(ref_rec.stored_path) if ref_rec else None
    if ref_path is None:
        for meta in KNOWN_VERSIONS:
            if meta["id"] == reference_id and meta["path"].is_file():
                ref_path = meta["path"]
                break
    table = build_coverage_table(reference_path=ref_path)
    return LocaleCoverageResponse(
        reference_path=table["reference_path"],
        reference_keys=table["reference_keys"],
        reference_found=table["reference_found"],
        locales=[LocaleCoverageRowModel(**row) for row in table.get("locales", [])],
        error=table.get("error"),
    )


@ext_router.get("/languages/coverage.csv", tags=["versions"], summary="Coverage table as CSV download")
def languages_coverage_csv(
    request: Request,
    reference_id: str = Query("ce-russian"),
) -> PlainTextResponse:
    store = get_store(request)
    ref_rec = store.get(reference_id)
    ref_path = Path(ref_rec.stored_path) if ref_rec else None
    if ref_path is None:
        for meta in KNOWN_VERSIONS:
            if meta["id"] == reference_id and meta["path"].is_file():
                ref_path = meta["path"]
                break
    table = build_coverage_table(reference_path=ref_path)
    return PlainTextResponse(
        coverage_to_csv(table),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="locale-coverage.csv"'},
    )


@ext_router.post("/languages/coverage/report", tags=["versions"], summary="Write coverage report to report/coverage/")
def languages_coverage_report(
    request: Request,
    reference_id: str = Query("ce-russian"),
) -> dict:
    store = get_store(request)
    ref_rec = store.get(reference_id)
    ref_path = Path(ref_rec.stored_path) if ref_rec else None
    if ref_path is None:
        for meta in KNOWN_VERSIONS:
            if meta["id"] == reference_id and meta["path"].is_file():
                ref_path = meta["path"]
                break
    out = write_coverage_report(reference_path=ref_path)
    return {"report_dir": str(out), "files": ["coverage.json", "coverage.csv"]}


@ext_router.get("/files/{file_id}/diff/{other_id}/udiff", tags=["analysis"],
                summary="Unified diff of changed/missing entries")
def file_diff_udiff(
    request: Request,
    file_id: str,
    other_id: str,
    filter: str = Query("changed", pattern="^(changed|missing|empty|token_mismatch|all)$"),
) -> PlainTextResponse:
    store = get_store(request)
    rec_a = _get_record(store, file_id)
    rec_b = _get_record(store, other_id)
    doc_a = store.document(file_id)
    doc_b = store.document(other_id)
    filters = ("changed", "missing", "empty", "token_mismatch") if filter == "all" else filter
    body = export_unified_diff(
        doc_a, doc_b,
        label_a=rec_a.name, label_b=rec_b.name,
        filters=filters,
    )
    return PlainTextResponse(
        body or "(no differences)\n",
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="diff-{file_id[:8]}-{other_id[:8]}.patch"'},
    )


@ext_router.post("/merge/preview", tags=["merge"], response_model=MergePreviewResponse,
                 summary="Preview first N merge changes without writing")
def merge_preview(
    request: Request,
    req: MergePreviewRequest,
    game_profile: str = Query("coh1", pattern="^(coh1|coh2|dow1|dow2)$"),
    strict_profile: bool = Query(False),
) -> MergePreviewResponse:
    store = get_store(request)
    _get_record(store, req.target_id)
    _get_record(store, req.source_id)
    raise_profile_strict(store, [req.target_id, req.source_id], game_profile, strict_profile)
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
    return MtStatusResponse(**{k: s.get(k, "" if k == "message" else 0)
                               for k in ("status", "progress", "total", "message")})


@ext_router.post("/mt/cancel", tags=["analysis"], summary="Cancel running MT job")
def mt_cancel() -> dict:
    from . import jobs
    job = jobs.latest_job()
    if job:
        jobs.cancel_job(job.id)
    return services.mt_status()


@ext_router.post("/mt/resume", tags=["analysis"], summary="Resume paused MT job")
def mt_resume() -> dict:
    from . import jobs
    job = jobs.latest_job()
    if job:
        jobs.resume_job(job.id)
    return services.mt_status()


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


@ext_router.get("/versions/patch-chain", tags=["versions"], response_model=PatchChainResponse,
                summary="Consecutive patch deltas across known English UCS editions")
def versions_patch_chain(request: Request) -> PatchChainResponse:
    store = get_store(request)
    documents = {}
    for vid, _ in TIMELINE_ORDER:
        rec = store.get(vid)
        if rec:
            documents[vid] = store.document(vid)
    result = build_patch_chain(documents)
    return PatchChainResponse(
        chain=[PatchChainStep(**step) for step in result["chain"]],
        reference=result["reference"],
    )


@ext_router.get("/depots", tags=["tools"], summary="Steam depot cards")
def list_depots() -> dict:
    exe = find_depotdownloader()
    return {
        "depots": DEPOT_CARDS,
        "depotdownloader": str(exe) if exe else None,
        "credentials_env": ["STEAM_USERNAME", "STEAM_PASSWORD", "STEAM_GUARD_CODE"],
    }


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
def batch_compare(
    request: Request,
    req: BatchCompareRequest,
    game_profile: str = Query("coh1", pattern="^(coh1|coh2|dow1|dow2)$"),
    strict_profile: bool = Query(False),
) -> BatchCompareResponse:
    store = get_store(request)
    for fid in req.file_ids:
        _get_record(store, fid)
    raise_profile_strict(store, req.file_ids, game_profile, strict_profile)
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


@ext_router.get("/files/{file_id}/game-profile", tags=["analysis"],
                summary="Classify UCS against CoH/DoW game profiles")
def file_game_profile(request: Request, file_id: str, profile: str = Query("coh1")) -> dict:
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    return {
        "classification": classify_document(doc),
        "validation": validate_against_profile(doc, profile),
    }


@ext_router.get("/sga/locale-scan", tags=["tools"], summary="Scan install for locale SGA archives")
def sga_locale_scan(install_path: str = Query(...)) -> dict:
    base = Path(install_path)
    if not base.exists():
        raise HTTPException(404, f"Path not found: {install_path}")
    archives = scan_install_locale_archives(base)
    return {"install_path": str(base), "archives": archives, "count": len(archives)}


@ext_router.post("/sga/extract-locales", tags=["tools"],
                 summary="Extract all locale UCS from install SGAs into uploads")
async def sga_extract_locales(request: Request, body: dict) -> dict:
    install_path = body.get("install_path", "")
    if not install_path:
        raise HTTPException(400, "install_path required")
    base = Path(install_path)
    if not base.exists():
        raise HTTPException(404, f"Path not found: {install_path}")
    store = get_store(request)
    scratch = store.generated_dir / f"sga-extract-{uuid.uuid4().hex}"
    raw = extract_all_locale_ucs(base, scratch)
    uploaded: list[dict] = []
    for item in raw:
        out = item.get("output")
        if not out or item.get("error"):
            continue
        out_path = Path(out)
        if out_path.suffix.lower() != ".ucs":
            continue
        rec = store.add_generated(out_path, out_path.name)
        uploaded.append({
            "file_id": rec.id,
            "download_url": f"/api/downloads/{rec.id}",
            "source_archive": item.get("archive"),
            "internal_path": item.get("internal_path"),
        })
    services.audit_log("sga_extract_locales", f"{len(uploaded)} UCS from {install_path}")
    return {
        "extracted": len(raw),
        "uploaded": len(uploaded),
        "files": uploaded,
        "errors": [r for r in raw if r.get("error")],
    }


@ext_router.get("/audit", tags=["meta"], response_model=AuditResponse,
                summary="Recent operations audit log")
def get_audit_log(limit: int = Query(50, ge=1, le=200)) -> AuditResponse:
    from .models import AuditEntry
    entries = [AuditEntry(**e) for e in services.get_audit(limit)]
    return AuditResponse(entries=entries)


@ext_router.get("/audit/export.csv", tags=["meta"], response_class=PlainTextResponse,
                summary="Export audit log as CSV")
def audit_export_csv(limit: int = Query(500, ge=1, le=5000)) -> PlainTextResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "action", "detail", "file_id"])
    for e in services.get_audit(limit):
        w.writerow([e.get("ts", ""), e.get("action", ""), e.get("detail", ""), e.get("file_id", "")])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                               headers={"Content-Disposition": 'attachment; filename="audit.csv"'})


# ---------------------------------------------------------- new endpoints
@ext_router.get("/sga/{path:path}/contents", tags=["tools"], summary="List SGA internal files")
def sga_contents(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"SGA not found: {path}")
    return list_sga_contents(p)


@ext_router.post("/sga/{path:path}/extract", tags=["tools"], summary="Extract file from SGA archive")
async def sga_extract(request: Request, path: str, body: dict) -> dict:
    """Extract an internal SGA file; UCS locale files are auto-uploaded."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"SGA not found: {path}")
    internal = body.get("internal_path", "")
    if not internal:
        raise HTTPException(400, "internal_path required")
    store = get_store(request)
    try:
        data, _ = extract_file(p, internal)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    out_name = Path(internal).name or "extracted.bin"
    out_path = store.generated_dir / f"sga-{uuid.uuid4().hex}-{out_name}"
    out_path.write_bytes(data)
    file_id = None
    download_url = None
    if out_name.lower().endswith(".ucs"):
        rec = store.add_generated(out_path, out_name)
        file_id = rec.id
        download_url = f"/api/downloads/{rec.id}"
        services.audit_log("sga_extract", f"{p.name}:{internal}", file_id=rec.id)
    else:
        services.audit_log("sga_extract", f"{p.name}:{internal}")
    return {
        "bytes": len(data),
        "internal_path": internal,
        "output_name": out_name,
        "file_id": file_id,
        "download_url": download_url,
    }


def _ucs_document_to_bytes(doc) -> bytes:
    from parser import BOM_LE, serialize
    text = serialize(doc.sorted_entries(), newline=doc.newline, trailing_newline=doc.trailing_newline)
    return BOM_LE + text.encode(doc.encoding)


@ext_router.post("/sga/{path:path}/inject-ucs", tags=["tools"],
                 summary="Replace locale UCS inside an SGA archive")
async def sga_inject_ucs(request: Request, path: str, body: dict) -> dict:
    """Pack a modified UCS from the file store back into an SGA copy."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"SGA not found: {path}")
    internal = body.get("internal_path", "")
    ucs_id = body.get("ucs_id", "")
    if not internal or not ucs_id:
        raise HTTPException(400, "internal_path and ucs_id required")
    store = get_store(request)
    _get_record(store, ucs_id)
    doc = store.document(ucs_id)
    raw = _ucs_document_to_bytes(doc)
    out_name = body.get("output_name") or f"{p.stem}-patched.sga"
    out_path = store.generated_dir / out_name
    try:
        inject_ucs_into_sga(p, internal, raw, out_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    gen = store.add_generated(out_path, out_name)
    services.audit_log("sga_inject_ucs", f"{p.name}:{internal}", file_id=ucs_id)
    return {
        "output": str(out_path),
        "bytes": out_path.stat().st_size,
        "internal_path": internal,
        "ucs_id": ucs_id,
        "download_id": gen.id,
        "download_url": f"/api/downloads/{gen.id}",
    }


@ext_router.post("/sga/pack", tags=["tools"], summary="Pack files into a new SGA archive")
def sga_pack(body: dict) -> dict:
    """Create SGA from ``{output, files: {internal_path: host_path}}``."""
    output = Path(body.get("output", "packed.sga"))
    file_map = body.get("files") or {}
    if not file_map:
        raise HTTPException(400, "files map required")
    payload: dict[str, bytes] = {}
    for internal, host in file_map.items():
        host_path = Path(host)
        if not host_path.is_file():
            raise HTTPException(404, f"Host file not found: {host}")
        payload[internal] = host_path.read_bytes()
    compress = bool(body.get("compress", False))
    pack_sga(output, payload, compress=compress)
    return {"output": str(output.resolve()), "files": len(payload), "bytes": output.stat().st_size}


@ext_router.get("/verify/checklist", tags=["analysis"], summary="In-game verification checklist (built-in IDs)")
def verify_checklist_builtin() -> dict:
    from verification_checklist import VERIFICATION_ITEMS
    return {
        "items": [
            {
                "key": i.key,
                "category": i.category,
                "label": i.label,
                "in_game_hint": i.in_game_hint,
                "expected_substrings": list(i.expected_substrings),
            }
            for i in VERIFICATION_ITEMS
        ],
    }


@ext_router.get("/files/{file_id}/verify", tags=["analysis"], summary="Run in-game QA checklist on upload")
def verify_file_checklist(request: Request, file_id: str) -> dict:
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    report = run_checklist(doc)
    report["file_id"] = file_id
    services.audit_log("verify_checklist", f"{report['passed']}/{report['total']} pass", file_id=file_id)
    return report


@ext_router.get("/files/{file_id}/tmx", tags=["files"], response_class=PlainTextResponse,
                summary="Export UCS to TMX (CAT tools)")
def export_file_tmx(
    request: Request,
    file_id: str,
    source_lang: str = Query("en"),
    target_lang: str = Query("en"),
) -> PlainTextResponse:
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    return PlainTextResponse(
        export_tmx(doc, source_lang=source_lang, target_lang=target_lang),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{file_id}.tmx"'},
    )


@ext_router.post("/files/{file_id}/tmx", tags=["files"], summary="Import TMX into new UCS upload")
async def import_file_tmx(request: Request, file_id: str, body: dict) -> dict:
    store = get_store(request)
    rec = _get_record(store, file_id)
    tmx_text = body.get("tmx", "")
    if not tmx_text:
        raise HTTPException(400, "tmx text required")
    target_lang = body.get("target_lang")
    entries = import_tmx(tmx_text, target_lang=target_lang)
    doc = store.document(file_id)
    out_path = store.generated_dir / f"tmx-{uuid.uuid4().hex}.ucs"
    write_file(out_path, sorted(entries.items()), encoding=doc.encoding, add_bom=doc.has_bom,
                newline=doc.newline, trailing_newline=doc.trailing_newline, overwrite=True)
    gen = store.add_generated(out_path, f"from-tmx-{rec.name}")
    return {"file_id": gen.id, "keys": len(entries)}


@ext_router.get("/campaigns/ranges", tags=["analysis"], summary="Campaign ID range map")
def campaigns_ranges() -> dict:
    return {"campaigns": campaign_ranges()}


@ext_router.post("/merge/threeway", tags=["merge"], summary="Three-way UCS merge")
def merge_threeway_api(request: Request, body: dict) -> dict:
    store = get_store(request)
    base_id = body.get("base")
    a_id = body.get("a")
    b_id = body.get("b")
    strategy = body.get("strategy", "prefer_a")
    if strategy not in ("prefer_a", "prefer_b", "manual_conflicts"):
        raise HTTPException(400, "strategy must be prefer_a, prefer_b, or manual_conflicts")
    for fid in (base_id, a_id, b_id):
        _get_record(store, fid)
    base = store.document(base_id)
    a_doc = store.document(a_id)
    b_doc = store.document(b_id)
    out_path = store.generated_dir / f"threeway-{uuid.uuid4().hex}.ucs"
    result = merge_threeway_and_write(base, a_doc, b_doc, out_path, strategy=strategy)
    gen = store.add_generated(out_path, "merged-threeway.ucs")
    services.audit_log("merge_threeway", f"{len(result.entries)} keys, {len(result.conflicts)} conflicts")
    services.fire_webhooks("merge_complete", {"file_id": gen.id, "keys": len(result.entries)})
    return {
        "download_id": gen.id,
        "download_url": f"/api/downloads/{gen.id}",
        "keys": len(result.entries),
        "conflicts": [
            {"key": c.key, "base": c.base, "a": c.a, "b": c.b}
            for c in result.conflicts
        ],
    }


@ext_router.post("/files/{file_id}/save", tags=["files"], summary="Save edited UCS as new upload")
async def save_file_edited(request: Request, file_id: str, body: dict) -> dict:
    store = get_store(request)
    rec = _get_record(store, file_id)
    entries = body.get("entries", [])
    if not entries:
        raise HTTPException(400, "entries required")
    parsed = [(int(e["key"]), str(e["value"])) for e in entries]
    out_path = store.generated_dir / f"edit-{uuid.uuid4().hex}.ucs"
    doc = store.document(file_id)
    write_file(out_path, sorted(parsed), encoding=doc.encoding, add_bom=doc.has_bom,
                newline=doc.newline, trailing_newline=doc.trailing_newline, overwrite=True)
    gen = store.add_generated(out_path, f"edited-{rec.name}")
    services.audit_log("editor_save", rec.name, file_id=gen.id)
    return {"file_id": gen.id, "download_url": f"/api/downloads/{gen.id}"}


@ext_router.get("/files/{file_id}/po", tags=["files"], response_class=PlainTextResponse,
                summary="Export UCS to PO/Gettext")
def export_file_po(request: Request, file_id: str) -> PlainTextResponse:
    store = get_store(request)
    _get_record(store, file_id)
    doc = store.document(file_id)
    return PlainTextResponse(export_po(doc), media_type="text/plain",
                               headers={"Content-Disposition": f'attachment; filename="{file_id}.po"'})


@ext_router.post("/files/{file_id}/po", tags=["files"], summary="Import PO into new UCS upload")
async def import_file_po(request: Request, file_id: str, body: dict) -> dict:
    store = get_store(request)
    rec = _get_record(store, file_id)
    po_text = body.get("po", "")
    if not po_text:
        raise HTTPException(400, "po text required")
    entries = import_po(po_text)
    doc = store.document(file_id)
    out_path = store.generated_dir / f"po-{uuid.uuid4().hex}.ucs"
    write_file(out_path, sorted(entries.items()), encoding=doc.encoding, add_bom=doc.has_bom,
                newline=doc.newline, trailing_newline=doc.trailing_newline, overwrite=True)
    gen = store.add_generated(out_path, f"from-po-{rec.name}")
    return {"file_id": gen.id, "keys": len(entries)}


@ext_router.post("/patch/build", tags=["merge"], response_model=PatchBuildResponse,
                 summary="Build subset UCS from ranges (+ optional changelog TSV)")
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
    changelog = "id\tvalue\n" + "\n".join(f"{k}\t{v}" for k, v in sorted(subset.items()))
    services.audit_log("patch_build", f"{len(subset)} keys", file_id=req.file_id)
    return PatchBuildResponse(
        download_id=gen.id, download_url=f"/api/downloads/{gen.id}", keys=len(subset),
        changelog_tsv=changelog,
    )


@ext_router.post("/patch/apply", tags=["merge"], response_model=PatchApplyResponse,
                 summary="Overlay patch UCS entries onto a base file")
def patch_apply(request: Request, req: PatchApplyRequest) -> PatchApplyResponse:
    store = get_store(request)
    base_rec = _get_record(store, req.base_id)
    _get_record(store, req.patch_id)
    base_doc = store.document(req.base_id)
    patch_doc = store.document(req.patch_id)
    merged, changed, added = apply_patch_overlay(base_doc, patch_doc)
    out_path = store.generated_dir / f"patched-{uuid.uuid4().hex}.ucs"
    write_file(
        out_path, sorted(merged.items()),
        encoding=base_doc.encoding, add_bom=base_doc.has_bom,
        newline=base_doc.newline, trailing_newline=base_doc.trailing_newline,
        overwrite=True,
    )
    gen = store.add_generated(out_path, f"patched-{base_rec.name}")
    services.audit_log(
        "patch_apply",
        f"{len(changed)} changed, {len(added)} added",
        file_id=req.base_id,
    )
    services.fire_webhooks("merge_complete", {
        "file_id": gen.id,
        "keys": len(merged),
        "changed": len(changed),
        "added": len(added),
        "kind": "patch_apply",
    })
    return PatchApplyResponse(
        download_id=gen.id,
        download_url=f"/api/downloads/{gen.id}",
        keys=len(merged),
        changed=len(changed),
        added=len(added),
    )


@ext_router.post("/tools/duplicate-probe", tags=["tools"], summary="Generate duplicate-ID probe UCS")
async def duplicate_probe_api(request: Request) -> dict:
    from duplicate_probe import probe_instructions, write_duplicate_probe

    store = get_store(request)
    out_path = store.generated_dir / "duplicate-probe.ucs"
    write_duplicate_probe(out_path, overwrite=True)
    gen = store.add_generated(out_path, "duplicate-probe.ucs")
    services.audit_log("duplicate_probe", "generated probe file")
    return {
        "file_id": gen.id,
        "download_url": f"/api/downloads/{gen.id}",
        "instructions": probe_instructions(out_path),
        "probe_key": 99999001,
    }


@ext_router.get("/install/script", tags=["tools"], summary="Install automation script")
def install_script(target: str = Query(...)) -> dict:
    target_path = Path(target)
    writable_roots = [Path.home(), Path.cwd(), Path("uploads")]
    is_safe = any(
        str(target_path.resolve()).startswith(str(r.resolve()))
        for r in writable_roots if r.exists()
    )
    script = (
        f'# Backup\nCopy-Item "{target}" "{target}.bak" -Force\n'
        f'# Install (run only after verifying paths)\n'
        f'Copy-Item ".\\RelicCOH.English.complete.ucs" "{target}" -Force\n'
    )
    if not is_safe and "Program Files" in str(target_path):
        script = (
            f"# ELEVATED INSTALL REQUIRED — target is under Program Files\n"
            f"# Run PowerShell as Administrator:\n{script}"
        )
    return {"target": str(target_path), "script": script, "requires_elevation": not is_safe}


@ext_router.post("/install/apply", tags=["tools"], summary="Apply install (user-writable paths only)")
def install_apply(body: dict) -> dict:
    if not body.get("confirm"):
        raise HTTPException(400, "confirm: true required")
    target = Path(body.get("target", ""))
    source = Path(body.get("source", "RelicCOH.English.complete.ucs"))
    if not source.exists():
        raise HTTPException(404, f"Source not found: {source}")
    if "Program Files" in str(target.resolve()):
        raise HTTPException(403, "Refusing to write under Program Files — use install/script for elevated commands")
    writable = [Path.home(), Path.cwd(), Path("uploads")]
    if not any(str(target.resolve()).startswith(str(r.resolve())) for r in writable if r.exists()):
        raise HTTPException(403, "Target must be under a user-writable path")
    target.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copyfile(source, target)
    services.audit_log("install_apply", str(target))
    return {"installed": str(target), "keys_source": str(source)}


@ext_router.post("/depot/fetch-instructions", tags=["tools"], summary="Depot download instructions")
def depot_fetch_instructions(body: dict) -> dict:
    lang = (body.get("language") or body.get("lang") or "french").lower()
    card = next((d for d in DEPOT_CARDS if d["language"].lower() == lang), DEPOT_CARDS[0])
    return {
        "language": card["language"],
        "command": card["command_template"],
        "expected_file": card.get("expected_file", "downloads/"),
        "depot_id": card["depot_id"],
        "app_id": card["app_id"],
        "note": "Or POST /api/depot/download with STEAM_USERNAME/STEAM_PASSWORD in env.",
        "upload_fallback": "POST /api/files with the downloaded UCS",
        "automated": find_depotdownloader() is not None,
    }


@ext_router.post("/depot/download", tags=["tools"], summary="Download locale UCS via DepotDownloader")
async def depot_download(request: Request, body: dict) -> dict:
    """Run DepotDownloader using env credentials (never stored server-side)."""
    lang = (body.get("language") or body.get("lang") or "french").lower()
    build_after = bool(body.get("build", False))
    try:
        result = download_depot_locale(
            lang,
            username=body.get("username"),
            password=body.get("password"),
            guard_code=body.get("steam_guard_code"),
        )
    except (ValueError, FileNotFoundError, TimeoutError) as exc:
        raise HTTPException(400, str(exc)) from exc

    services.audit_log("depot_download", f"{lang} exit={result.get('exit_code')}")
    if not result.get("success"):
        return result

    out: dict = {"download": result}
    if build_after:
        out["build"] = run_locale_build(lang)
        spec = DEPOT_SPECS.get(lang)
        if spec and spec.build_script:
            complete = Path(f"RelicCOH.{spec.language.title()}.complete.ucs")
            if complete.exists():
                store = get_store(request)
                vid = f"{lang}-complete"
                rec = store.register_version(
                    vid, complete.name, complete,
                    origin="Depot download + build", completeness="Union build",
                    notes=f"Built after depot {result.get('depot_id')}",
                )
                out["version_id"] = rec.id if rec else vid
    return out


@ext_router.post("/depot/import", tags=["tools"], summary="Import depot UCS and build complete locale")
def depot_import(request: Request, body: dict | None = None) -> dict:
    body = body or {}
    lang = (body.get("language") or "french").lower()
    spec = DEPOT_SPECS.get(lang)
    if not spec or not spec.build_script:
        raise HTTPException(400, f"No build pipeline for language {lang}")
    nsv = Path(body.get("nsv_path", DOWNLOADS_DIR / spec.nsv_filename))
    if not nsv.is_file():
        alt = DOWNLOADS_DIR / spec.nsv_filename.replace("RelicCOH.", "RelicCoH.")
        nsv = alt if alt.is_file() else nsv
    if not nsv.is_file():
        raise HTTPException(404, f"Place UCS at {spec.nsv_filename} or run POST /api/depot/download")
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, spec.build_script, "--nsv", str(nsv)],
        capture_output=True, text=True, cwd=str(Path.cwd()),
    )
    out = Path(f"RelicCOH.{spec.language.title()}.complete.ucs")
    store = get_store(request)
    if out.exists():
        rec = store.register_version(
            f"{lang}-complete", out.name, out,
            origin="Built via depot import", completeness="Union build",
            notes=f"Official {spec.language} NSV + placeholders",
        )
        return {"built": True, "language": lang, "version_id": rec.id if rec else None, "stdout": result.stdout[-500:]}
    return {"built": False, "language": lang, "stderr": result.stderr[-500:]}


@ext_router.post("/community/hash", tags=["meta"], summary="Register community UCS hash metadata")
def community_hash_register(body: dict) -> dict:
    from .db import get_db
    sha = body.get("sha256", "").lower()
    if not sha or len(sha) != 64:
        raise HTTPException(400, "sha256 required (64 hex chars)")
    get_db().execute(
        "INSERT OR REPLACE INTO community_hashes(sha256, key_count, label, registered_at) VALUES (?,?,?,?)",
        (sha, int(body.get("key_count", 0)), body.get("label", ""), __import__("time").time()),
    )
    return {"registered": sha}


@ext_router.get("/community/hashes", tags=["meta"], summary="List community hash registry")
def community_hash_list() -> dict:
    from .db import get_db
    rows = get_db().fetchall("SELECT sha256, key_count, label, registered_at FROM community_hashes")
    return {"hashes": [dict(r) for r in rows]}


@ext_router.post("/webhooks", tags=["meta"], summary="Register webhook URL")
def register_webhook(body: dict) -> dict:
    from .db import get_db
    wid = uuid.uuid4().hex
    events = body.get("events", ["merge_complete", "compare_complete"])
    get_db().execute(
        "INSERT INTO webhooks(id, url, events, created_at) VALUES (?,?,?,?)",
        (wid, body.get("url", ""), json.dumps(events), __import__("time").time()),
    )
    return {"id": wid, "url": body.get("url"), "events": events}


@ext_router.get("/webhooks", tags=["meta"], summary="List registered webhooks")
def list_webhooks() -> dict:
    from .db import get_db
    rows = get_db().fetchall("SELECT id, url, events, created_at FROM webhooks ORDER BY created_at")
    hooks = []
    for row in rows:
        hooks.append({
            "id": row["id"],
            "url": row["url"],
            "events": json.loads(row["events"] or "[]"),
            "created_at": row["created_at"],
        })
    return {"webhooks": hooks}


@ext_router.get("/webhooks/deliveries", tags=["meta"], summary="Webhook delivery log")
def list_webhook_deliveries(limit: int = Query(50, ge=1, le=500)) -> dict:
    from .db import get_db
    rows = get_db().fetchall(
        """SELECT id, event, url, success, status_code, error, payload_json,
                  attempt, dead_letter, created_at
           FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )
    deliveries = []
    for row in rows:
        deliveries.append({
            "id": row["id"],
            "event": row["event"],
            "url": row["url"],
            "success": bool(row["success"]),
            "status_code": row["status_code"],
            "error": row["error"] or "",
            "attempt": row["attempt"] if "attempt" in row.keys() else 1,
            "dead_letter": bool(row["dead_letter"]) if "dead_letter" in row.keys() else False,
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": row["created_at"],
        })
    return {"deliveries": deliveries}


@ext_router.post("/webhooks/retry-dead-letters", tags=["meta"], summary="Retry failed webhook deliveries")
def retry_webhook_dead_letters(limit: int = Query(20, ge=1, le=100)) -> dict:
    return services.retry_dead_letter_webhooks(limit=limit)


@ext_router.get("/projects", tags=["meta"], summary="List workspaces/projects")
def list_projects() -> dict:
    from .db import get_db
    rows = get_db().fetchall("SELECT * FROM projects ORDER BY created_at")
    return {"projects": [dict(r) for r in rows]}


@ext_router.post("/projects", tags=["meta"], summary="Create workspace/project")
def create_project(body: dict) -> dict:
    from .db import get_db
    pid = uuid.uuid4().hex
    get_db().execute(
        "INSERT INTO projects(id, name, created_at, notes) VALUES (?,?,?,?)",
        (pid, body.get("name", "Untitled"), __import__("time").time(), body.get("notes", "")),
    )
    return {"id": pid, "name": body.get("name")}
