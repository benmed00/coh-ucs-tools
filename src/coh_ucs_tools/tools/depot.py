"""Steam DepotDownloader automation for CoH locale UCS files.

Credentials are read from environment variables only (never logged or stored):

* ``STEAM_USERNAME`` / ``STEAM_PASSWORD`` — Steam account with CoH owned
* ``STEAM_GUARD_CODE`` — optional one-time 2FA code when required

Requires `DepotDownloader <https://github.com/SteamRE/DepotDownloader>`_ on PATH
or at ``DEPOTDOWNLOADER_PATH``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

from coh_ucs_tools.config.paths import DOWNLOADS_DIR


@dataclass(frozen=True)
class DepotSpec:
    language: str
    app_id: int
    depot_id: int
    depot_lang: str
    nsv_filename: str
    ucs_glob: str
    build_script: str  # module path, e.g. coh_ucs_tools.locale.builders.french
    depot_verified: bool = False
    steamdb_note: str = ""


DEPOT_SPECS: dict[str, DepotSpec] = {
    "english": DepotSpec(
        "english", 228200, 228201, "english",
        "RelicCOH.English.NSV.ucs", "*English*.ucs", "",
    ),
    "french": DepotSpec(
        "french", 4560, 4565, "french",
        "RelicCOH.French.NSV.ucs", "*French*.ucs", "coh_ucs_tools.locale.builders.french",
        depot_verified=True,
        steamdb_note="Legacy Edition language depot 4565 (SteamDB app 4560).",
    ),
    "german": DepotSpec(
        "german", 4560, 4564, "german",
        "RelicCOH.German.NSV.ucs", "*German*.ucs", "coh_ucs_tools.locale.builders.german",
        depot_verified=True,
        steamdb_note="Legacy Edition language depot 4564 (SteamDB app 4560).",
    ),
    "spanish": DepotSpec(
        "spanish", 4560, 4566, "spanish",
        "RelicCOH.Spanish.NSV.ucs", "*Spanish*.ucs", "coh_ucs_tools.locale.builders.spanish",
        depot_verified=True,
        steamdb_note="Legacy Edition language depot 4566 (SteamDB app 4560).",
    ),
    "italian": DepotSpec(
        "italian", 4560, 4567, "italian",
        "RelicCOH.Italian.NSV.ucs", "*Italian*.ucs", "coh_ucs_tools.locale.builders.italian",
        depot_verified=True,
        steamdb_note="Italian language depot 4567 (SteamDB app 4560, verified community listing).",
    ),
    "polish": DepotSpec(
        "polish", 4560, 4568, "polish",
        "RelicCOH.Polish.NSV.ucs", "*Polish*.ucs", "coh_ucs_tools.locale.builders.polish",
        depot_verified=True,
        steamdb_note="Polish language depot 4568 (SteamDB app 4560; sequential with DE/FR/ES/IT depots).",
    ),
}


def list_depot_specs() -> list[dict]:
    return [
        {
            "language": s.language,
            "app_id": s.app_id,
            "depot_id": s.depot_id,
            "depot_lang": s.depot_lang,
            "expected_file": str(DOWNLOADS_DIR / s.nsv_filename),
            "build_script": s.build_script or None,
            "depot_verified": s.depot_verified,
            "steamdb_note": s.steamdb_note or None,
            "command_template": (
                f"DepotDownloader -app {s.app_id} -depot {s.depot_id} -lang {s.depot_lang}"
            ),
        }
        for s in DEPOT_SPECS.values()
    ]


def find_depotdownloader() -> Path | None:
    """Locate DepotDownloader executable."""
    env_path = os.environ.get("DEPOTDOWNLOADER_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
    found = shutil.which("DepotDownloader") or shutil.which("depotdownloader")
    if found:
        return Path(found)
    for candidate in (
        Path.home() / "DepotDownloader" / "DepotDownloader.exe",
        Path(r"C:\Tools\DepotDownloader\DepotDownloader.exe"),
        Path("/usr/local/bin/DepotDownloader"),
    ):
        if candidate.is_file():
            return candidate
    return None


def steam_credentials(
    *,
    username: str | None = None,
    password: str | None = None,
    guard_code: str | None = None,
) -> tuple[str, str, str | None]:
    user = (username or os.environ.get("STEAM_USERNAME", "")).strip()
    pw = (password or os.environ.get("STEAM_PASSWORD", "")).strip()
    guard = (guard_code or os.environ.get("STEAM_GUARD_CODE", "")).strip() or None
    if not user or not pw:
        raise ValueError(
            "Steam credentials required. Set STEAM_USERNAME and STEAM_PASSWORD "
            "environment variables or pass username/password to the API."
        )
    return user, pw, guard


def _find_ucs_files(root: Path, pattern: str) -> list[Path]:
    hits: list[Path] = []
    for p in root.rglob("*.ucs"):
        if p.match(pattern) or pattern.strip("*").lower() in p.name.lower():
            hits.append(p)
    return sorted(hits, key=lambda x: x.stat().st_size, reverse=True)


def download_depot_locale(
    language: str,
    *,
    username: str | None = None,
    password: str | None = None,
    guard_code: str | None = None,
    output_dir: Path | str | None = None,
    timeout_s: int = 600,
) -> dict:
    """Run DepotDownloader and copy the largest matching UCS to downloads/."""
    lang = language.lower()
    spec = DEPOT_SPECS.get(lang)
    if spec is None:
        raise ValueError(f"Unknown language {language!r}. Known: {', '.join(DEPOT_SPECS)}")

    exe = find_depotdownloader()
    if exe is None:
        raise FileNotFoundError(
            "DepotDownloader not found. Install from https://github.com/SteamRE/DepotDownloader "
            "and add to PATH or set DEPOTDOWNLOADER_PATH."
        )

    user, pw, guard = steam_credentials(username=username, password=password, guard_code=guard_code)
    work_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="coh-depot-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS_DIR / spec.nsv_filename

    cmd = [
        str(exe),
        "-app", str(spec.app_id),
        "-depot", str(spec.depot_id),
        "-username", user,
        "-password", pw,
        "-dir", str(work_dir),
    ]
    if guard:
        cmd.extend(["-steamguard", guard])

    logger.info("Running DepotDownloader for %s depot %s", lang, spec.depot_id)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"DepotDownloader timed out after {timeout_s}s") from exc

    result = {
        "language": lang,
        "app_id": spec.app_id,
        "depot_id": spec.depot_id,
        "exit_code": proc.returncode,
        "work_dir": str(work_dir),
        "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
    }

    if proc.returncode != 0:
        result["error"] = "DepotDownloader failed — check credentials, 2FA (STEAM_GUARD_CODE), and game ownership"
        return result

    candidates = _find_ucs_files(work_dir, spec.ucs_glob)
    if not candidates:
        candidates = _find_ucs_files(work_dir, "*.ucs")
    if not candidates:
        result["error"] = f"No .ucs files found under {work_dir}"
        return result

    source = candidates[0]
    shutil.copy2(source, dest)
    result.update({
        "source_ucs": str(source),
        "dest": str(dest),
        "bytes": dest.stat().st_size,
        "success": True,
    })
    return result


def run_locale_build(language: str, nsv_path: Path | None = None) -> dict:
    """Run the union-build module for *language* after NSV download."""
    import importlib
    import io
    from contextlib import redirect_stderr, redirect_stdout

    spec = DEPOT_SPECS.get(language.lower())
    if not spec or not spec.build_script:
        return {"built": False, "reason": "no build script for this language"}
    nsv = nsv_path or (DOWNLOADS_DIR / spec.nsv_filename)
    if not nsv.is_file():
        return {"built": False, "reason": f"NSV not found: {nsv}"}
    mod = importlib.import_module(spec.build_script)
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mod.main(["--nsv", str(nsv)])
    stdout = out.getvalue()
    stderr = err.getvalue()
    return {
        "built": code == 0,
        "exit_code": code,
        "stdout_tail": stdout[-800:] if stdout else "",
        "stderr_tail": stderr[-800:] if stderr else "",
    }
