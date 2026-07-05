# Backlog

Prioritized roadmap for the CoH UCS Toolkit.

## Status overview

P1 and P2 items are complete. P3 items are mostly complete or partial.

## Wave 7 (completed)

| Item | Deliverable |
|---|---|
| SGA per-file compression | `pack_sga(compress_paths=…)`; `repack_sga` preserves each entry's zlib flag from template |
| Game profile in analysis panel | Upload page shows classification mismatch vs selected profile; links to Games |
| Playwright UI tests | E2E navigates merge-wizard, depots, upload (profile selector), settings |
| CoH2 / DoW fixtures | `tests/fixture_ucs.py` synthetic UCS files for profile classification regression |
| Webhook notifications | `fire_webhooks` on `/api/merge`, batch compare, patch apply; `GET /api/webhooks` |

## Wave 8 (completed)

| Item | Deliverable |
|---|---|
| Webhook delivery log | `webhook_deliveries` table; logged on fire; `GET /api/webhooks/deliveries`; Settings UI |
| SGA inject from UI | Inject panel in SGA browser after archive browse; remembers last extract |
| Profile strict on compare/merge | `game_profile` + `strict_profile` on compare, merge, preview, batch compare; UI profile bar |
| SEO sitemap test stability | About-page priority asserted in URL chunk, not global sitemap |

## Wave 9 (completed)

| Item | Deliverable |
|---|---|
| Profile metadata on uploads | `detected_profile` + `profile_confidence` on `StoredFile`/SQLite; shown in file list |
| Webhook retry / dead letter | 3-attempt backoff in `fire_webhooks`; `dead_letter` flag; `POST /api/webhooks/retry-dead-letters` |
| SGA inject from editor | Inject panel after editor save when SGA context in sessionStorage |
| OAuth/session expiry UX | `session_expires_in_s` on `/api/auth/status`; warnings in Settings |

## Suggested next wave

| Item | Notes |
|---|---|
| Real CoH2 UCS samples | Replace synthetic fixtures when sample files available |
| Backfill profile metadata | CLI to classify existing uploads in SQLite |
| Webhook HMAC signatures | Sign outbound webhook payloads |
| Profile filter on file list | UI filter by detected_profile |
| Scheduled dead-letter retry | Background job or cron endpoint |
