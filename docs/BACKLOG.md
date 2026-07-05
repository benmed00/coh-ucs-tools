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

## Suggested next wave

| Item | Notes |
|---|---|
| Real CoH2 UCS samples | Replace synthetic fixtures when sample files available |
| Webhook retry / dead-letter queue | Re-attempt failed deliveries with backoff |
| SGA inject from editor | One-click inject after save in entry editor |
| Profile metadata on file records | Persist detected profile on upload for faster list views |
| OAuth token refresh UX | Surface expiry and re-login in settings |
