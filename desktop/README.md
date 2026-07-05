# Desktop shell (Tauri / Electron)

The web toolkit can be wrapped as a native desktop app that embeds the FastAPI
server and opens the SPA in a webview.

## Option A — Tauri (recommended, smaller binary)

1. Install [Rust](https://rustup.rs/) and [Tauri prerequisites](https://tauri.app/start/prerequisites/).
2. From this directory:

```powershell
npm create tauri-app@latest coh-ucs-desktop -- --template vanilla
cd coh-ucs-desktop
```

3. In `src-tauri/tauri.conf.json`, set `devUrl` / `frontendDist` to `http://127.0.0.1:8000`.
4. Add a sidecar or spawn script that runs:

```powershell
python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000
```

5. `npm run tauri dev` for development; `npm run tauri build` for installers.

## Option B — Electron

1. `npm init -y && npm install electron wait-on`
2. Main process starts uvicorn, then loads `http://127.0.0.1:8000`.
3. Package with `electron-builder` (Windows NSIS).

## Notes

* Point `UCS_WEBAPP_UPLOADS` and `SQLITE_PATH` at a user-writable app data folder.
* Do not bundle copyrighted `.ucs` game files in the installer.
* API key (`UCS_API_KEY`) is optional for local-only use.
