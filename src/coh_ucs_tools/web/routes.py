"""Single source of truth for SPA route slugs and metadata."""

from __future__ import annotations

# Path-based SPA routes (slug, page title, meta description).
SPA_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Dashboard", "Overview of uploaded UCS files and localization stats."),
    ("about", "About", "What CoH UCS Tools is, how UCS localization works, and who it is for."),
    ("upload", "Upload & Analyze", "Upload Company of Heroes .ucs files for encoding detection, validation, and entry browsing."),
    ("compare", "Compare UCS Files", "Compare two UCS localization files for coverage percentages and missing ID ranges."),
    ("diff", "UCS Diff", "Side-by-side diff of UCS localization entries between two files."),
    ("languages", "Languages & Versions", "Browse known CoH1 localization versions, locales, and built-in registry files."),
    ("search", "Search Entries", "Full-text search across UCS localization entries by ID or translated text."),
    ("merge-wizard", "Merge Wizard", "Safely merge missing IDs between UCS files with placeholder or verbatim copy modes."),
    ("validator", "UCS Validator", "Validate UCS encoding, BOM, CRLF line endings, duplicates, and line format."),
    ("verify", "Verification Checklist", "Run the UCS verification checklist against an uploaded localization file."),
    ("translation", "PO / TMX Export", "Export UCS entries to gettext PO or TMX translation interchange formats."),
    ("tools", "Tools & References", "Curated external tools and community references for Company of Heroes modding."),
    ("settings", "Settings", "Configure API key, locale preferences, and console settings."),
    ("merge", "Merge", "Merge two UCS localization files."),
    ("ranges", "Missing ID Ranges", "Inspect contiguous missing ID ranges between UCS files."),
    ("install", "Install Guide", "Install and deploy the CoH UCS Tools web application."),
    ("mt", "Machine Translation Lab", "Cross-check UCS translations with machine translation tools."),
    ("timeline", "Localization Timeline", "Timeline of localization file versions and changes."),
    ("depots", "Depots & Sources", "Browse CoH depot sources and built-in localization registries."),
    ("patch", "Patch Builder", "Build localization patch files from UCS diffs."),
    ("sga", "SGA Archive Scanner", "Scan Company of Heroes install archives for locale UCS files."),
    ("glossary", "Glossary", "Localization glossary terms for Company of Heroes modding."),
    ("bookmarks", "Bookmarks", "Saved UCS entry bookmarks."),
    ("editor", "Entry Editor", "Edit individual UCS localization entries."),
    ("campaigns", "Campaigns", "Campaign-specific UCS localization coverage."),
    ("games", "Game Profiles", "Game profile UCS localization analysis."),
)

SPA_SLUGS: frozenset[str] = frozenset(slug for slug, _, _ in SPA_ROUTES)
APP_ROUTE_SLUGS: list[str] = [slug for slug, _, _ in SPA_ROUTES]

__all__ = ["SPA_ROUTES", "SPA_SLUGS", "APP_ROUTE_SLUGS"]
