"""Shared API dependencies and registries."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request

from .models import FileSummary
from .store import FileStore, StoredFile

#: Built-in registry of known Company of Heroes 1 UCS versions.
KNOWN_VERSIONS: list[dict] = [
    {
        "id": "thq-retail-english",
        "name": "RelicCOH.English.ucs (THQ retail)",
        "path": Path(r"c:\Program Files (x86)\THQ\Company of Heroes\Engine\Locale\English\RelicCOH.English.ucs"),
        "origin": "Original THQ retail install (2006), base game only",
        "completeness": "Base game only — pre-Opposing Fronts, 8,578 keys",
        "notes": "The old disc-era English file. Lacks every id added by Opposing Fronts, "
                 "Tales of Valor and later patches; merging against a Complete Edition file "
                 "leaves ~13.7k gaps.",
    },
    {
        "id": "ce-russian",
        "name": "RelicCOH.Russian.ucs (Complete Edition)",
        "path": Path(r"c:\Games\Company of Heroes - Complete Edition\CoH\Engine\Locale\Russian\RelicCOH.Russian.ucs"),
        "origin": "Company of Heroes — Complete Edition, Russian locale",
        "completeness": "Complete for CE content — 22,170 keys",
        "notes": "The Russian Complete Edition localization. Its id set is the usual "
                 "reference when hunting for strings missing from old English files.",
    },
    {
        "id": "nsv-english",
        "name": "RelicCOH.English.NSV.ucs (New Steam Version)",
        "path": Path("downloads/RelicCOH.English.NSV.ucs"),
        "origin": "New Steam Version (app 228200), community-shared official file",
        "completeness": "Complete — 22,523 keys, zero <MISSING> placeholders",
        "notes": "The full official English localization shipped with the New Steam Version. "
                 "Covers 100% of the Russian CE id set. Recovered via the Steam forums thread.",
    },
    {
        "id": "complete-english",
        "name": "RelicCOH.English.complete.ucs (union build)",
        "path": Path("RelicCOH.English.complete.ucs"),
        "origin": "Built by this toolkit: NSV English + 157 legacy-only THQ retail keys",
        "completeness": "Superset — 22,680 keys, nothing missing",
        "notes": "Union of the NSV official English text and the handful of ids that only "
                 "exist in the old THQ retail file. The most complete English UCS known.",
    },
]

# Optional union builds — registered at startup when present on disk.
LOCALE_VERSIONS: list[dict] = [
    {
        "id": "french-complete",
        "name": "RelicCOH.French.complete.ucs",
        "path": Path("RelicCOH.French.complete.ucs"),
        "origin": "Built by build_french.py",
        "completeness": "Official French NSV union + placeholders",
        "notes": "Requires recovered French NSV from depot 4565.",
    },
    {
        "id": "german-complete",
        "name": "RelicCOH.German.complete.ucs",
        "path": Path("RelicCOH.German.complete.ucs"),
        "origin": "Built by build_german.py",
        "completeness": "Official German NSV union + placeholders",
        "notes": "Requires recovered German NSV from depot 4564.",
    },
    {
        "id": "spanish-complete",
        "name": "RelicCOH.Spanish.complete.ucs",
        "path": Path("RelicCOH.Spanish.complete.ucs"),
        "origin": "Built by build_spanish.py",
        "completeness": "Official Spanish NSV union + placeholders",
        "notes": "Requires recovered Spanish NSV from depot 4566.",
    },
    {
        "id": "italian-complete",
        "name": "RelicCOH.Italian.complete.ucs",
        "path": Path("RelicCOH.Italian.complete.ucs"),
        "origin": "Built by build_italian.py",
        "completeness": "Official Italian NSV union + placeholders",
        "notes": "Requires recovered Italian NSV from depot 4567.",
    },
    {
        "id": "polish-complete",
        "name": "RelicCOH.Polish.complete.ucs",
        "path": Path("RelicCOH.Polish.complete.ucs"),
        "origin": "Built by build_polish.py",
        "completeness": "Official Polish NSV union + placeholders",
        "notes": "Requires recovered Polish NSV from depot 4568.",
    },
    {
        "id": "arabic-mt",
        "name": "RelicCOH.Arabic.MT.ucs",
        "path": Path("RelicCOH.Arabic.MT.ucs"),
        "origin": "Built by build_arabic.py (machine translation)",
        "completeness": "Unofficial MT from English complete",
        "notes": "Fan MT artifact — not official Relic text.",
    },
]

EXTERNAL_TOOLS: list[dict] = [
    {
        "name": "vscode-relic-ucs",
        "url": "https://github.com/Janne252/vscode-relic-ucs",
        "category": "Editor support",
        "description": "VS Code syntax highlighting for Relic .ucs localization files — "
                       "tab-separated ids get proper token colors instead of a wall of text.",
    },
    {
        "name": "SteamDB — CoH (app 4560)",
        "url": "https://steamdb.info/app/4560/",
        "category": "Depot intel",
        "description": "Depot and manifest history for the legacy Steam release of Company of "
                       "Heroes. Handy for figuring out which build shipped which locale files.",
    },
    {
        "name": "SteamDB — CoH New Steam Version (app 228200)",
        "url": "https://steamdb.info/app/228200/",
        "category": "Depot intel",
        "description": "The New Steam Version app. Its English depot carries the complete "
                       "22,523-key RelicCOH.English.ucs this toolkit uses as reference.",
    },
    {
        "name": "DepotDownloader",
        "url": "https://github.com/SteamRE/DepotDownloader",
        "category": "Depot intel",
        "description": "Steam depot downloader built on SteamKit2. Pull historic depot "
                       "manifests (including locale files) straight from Steam's CDN.",
    },
    {
        "name": "Corsix's Mod Studio",
        "url": "https://modstudio.corsix.org/",
        "category": "Modding",
        "description": "The classic CoH/DoW modding suite — opens SGA archives, RGD attribute "
                       "trees and friends. Where most UCS ids ultimately point.",
    },
    {
        "name": "Steam forums — NSV English UCS thread",
        "url": "https://steamcommunity.com/app/228200/discussions/0/353915847943232144/",
        "category": "Community",
        "description": "The community thread sharing the official New Steam Version English "
                       "localization file — the source of our complete reference text.",
    },
    {
        "name": "GameSaveInfo — Company of Heroes",
        "url": "https://www.gamesave.info/game/company-of-heroes/",
        "category": "Reference",
        "description": "Documented file locations for CoH installs — useful when hunting down "
                       "where a given edition keeps its Locale directory.",
    },
]

SGA_PLUGIN_TOOLS: list[dict] = [
    {"name": "Corsix Mod Studio", "url": "https://modstudio.corsix.org/",
     "category": "SGA / modding", "description": "Open and edit Relic SGA archives."},
    {"name": "SGA Reader (community)", "url": "https://github.com/search?q=relic+sga",
     "category": "SGA tools", "description": "Community tools for extracting Relic archive formats."},
]


def get_store(request: Request) -> FileStore:
    return request.app.state.store


def _summary(rec: StoredFile) -> FileSummary:
    return FileSummary(**{k: getattr(rec, k) for k in FileSummary.model_fields})


def _get_record(store: FileStore, file_id: str) -> StoredFile:
    rec = store.get(file_id)
    if rec is None:
        raise HTTPException(404, f"No file with id {file_id!r}")
    return rec


def raise_profile_strict(
    store: FileStore,
    file_ids: list[str],
    game_profile: str,
    strict_profile: bool,
) -> None:
    if not strict_profile:
        return
    from game_profiles import profile_strict_mismatches

    items = [(fid, store.document(fid)) for fid in file_ids]
    mismatches = profile_strict_mismatches(items, game_profile)
    if mismatches:
        raise HTTPException(
            422,
            detail={
                "message": f"One or more files do not match profile {game_profile!r}",
                "mismatches": mismatches,
            },
        )
