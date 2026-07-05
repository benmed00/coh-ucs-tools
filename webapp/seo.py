"""SEO helpers: site metadata, sitemap, index.html injection, and robots.txt."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Primary UI origin (GitHub Pages). Fly.io serves the same UI but canonical
# tags point here to avoid duplicate-content signals in search engines.
CANONICAL_UI_URL = "https://benmed00.github.io/coh-ucs-tools"
GITHUB_PAGES_URL = CANONICAL_UI_URL
API_ORIGIN = "https://coh-ucs-tools.fly.dev"
GITHUB_PAGES_BASE_PATH = "/coh-ucs-tools"

SITE_NAME = "CoH UCS Tools"
SITE_TAGLINE = "Company of Heroes localization command console"
SITE_DESCRIPTION = (
    "Analyze, validate, compare, and merge Company of Heroes .ucs localization files. "
    "UTF-16-LE parser, duplicate detection, merge wizard, PO/TMX export, and REST API."
)
SITE_KEYWORDS = (
    "Company of Heroes, CoH, UCS, localization, translation, modding, "
    "Relic, UTF-16, game localization, merge, validator"
)
GITHUB_REPO = "https://github.com/benmed00/coh-ucs-tools"
TWITTER_HANDLE = ""  # set when available

# Google Search Console (https://benmed00.github.io/coh-ucs-tools/)
# Override with UCS_GOOGLE_SITE_VERIFICATION env if token rotates.
DEFAULT_GOOGLE_SITE_VERIFICATION = "TOf-uBdZbfItuxtpcXuWEJ5ljEYSxwWw7Sorw9DDYTM"
GOOGLE_VERIFICATION_HTML = "google34239ced659ea41b.html"

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

_SITEMAP_META: dict[str, tuple[str, str]] = {
    "dashboard": ("weekly", "1.0"),
    "about": ("monthly", "0.9"),
}

ABOUT_FAQ: tuple[tuple[str, str], ...] = (
    (
        "What is a Company of Heroes UCS file?",
        "UCS files are Relic's UTF-16-LE localization tables. Each line is "
        "numeric_id<TAB>text with a FF FE byte-order mark, CRLF line endings, and no comment syntax.",
    ),
    (
        "Why do I see $559200 No Key in-game?",
        "The CoH engine renders $id No Key when a localization id exists in the scenario "
        "but is missing from the active .ucs file. CoH UCS Tools finds those gaps by comparing versions.",
    ),
    (
        "Can this tool invent missing translations?",
        "No. Merge modes only copy existing text or insert <MISSING> placeholders — "
        "original uploads are never modified in place.",
    ),
    (
        "Does it work with Tales of Valor and Opposing Fronts?",
        "Yes. Upload any CoH1 RelicCOH.*.ucs locale file; the validator checks encoding, "
        "duplicates, and line format regardless of campaign or expansion.",
    ),
    (
        "Is there an API for automation?",
        "Yes. The same parser and merge logic runs as a REST API on Fly.io with OpenAPI docs at /docs.",
    ),
)

API_DOC_PATHS: tuple[tuple[str, str, str], ...] = (
    ("/docs", "API Documentation", "Interactive Swagger UI for the CoH UCS Tools REST API."),
    ("/redoc", "API Reference", "ReDoc reference for the CoH UCS Tools REST API."),
)

_SPA_RESERVED_PREFIXES = frozenset({
    "api", "static", "docs", "redoc", "openapi.json", "robots.txt", "sitemap.xml", "favicon.ico",
})

SEO_HEAD_START = "<!-- SEO:HEAD -->"
SEO_HEAD_END = "<!-- /SEO:HEAD -->"
SEO_NOSCRIPT_START = "<!-- SEO:NOSCRIPT -->"
SEO_NOSCRIPT_END = "<!-- /SEO:NOSCRIPT -->"


def ui_site_url() -> str:
    """Return canonical UI origin (no trailing slash)."""
    url = os.environ.get("UCS_SITE_URL", CANONICAL_UI_URL).strip().rstrip("/")
    return url or CANONICAL_UI_URL


def api_origin() -> str:
    """Return API origin for OpenAPI doc URLs in sitemaps."""
    url = os.environ.get("UCS_API_ORIGIN", API_ORIGIN).strip().rstrip("/")
    return url or API_ORIGIN


def site_url() -> str:
    """Alias for canonical UI origin."""
    return ui_site_url()


def og_image_url(base: str | None = None) -> str:
    origin = (base or ui_site_url()).rstrip("/")
    return f"{origin}/icons/og-image.png"


def page_title_suffix() -> str:
    return f"{SITE_NAME} — localization command console"


def route_seo_map() -> dict[str, dict[str, str]]:
    return {
        slug: {"title": title, "description": desc}
        for slug, title, desc in SPA_ROUTES
    }


def _split_origin(url: str) -> tuple[str, str]:
    """Return (scheme+host origin, path prefix without trailing slash)."""
    parsed = urlparse(url.rstrip("/") + "/")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    prefix = parsed.path.rstrip("/")
    return origin, prefix


def canonical_path(slug: str, *, base_path: str = "") -> str:
    """Return path portion for canonical URLs (path-based routing)."""
    prefix = base_path.rstrip("/")
    if not slug or slug == "dashboard":
        return f"{prefix}/" if prefix else "/"
    return f"{prefix}/{slug}" if prefix else f"/{slug}"


def sitemap_lastmod() -> str:
    """Return YYYY-MM-DD from latest git commit touching webapp/, else today."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", "webapp/"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
        if result.returncode == 0:
            stamp = result.stdout.strip()
            if stamp:
                return stamp[:10]
    except (OSError, subprocess.SubprocessError):
        pass
    return date.today().isoformat()


def indexnow_key() -> str:
    """Return IndexNow API key from env, or empty string if unset."""
    return os.environ.get("UCS_INDEXNOW_KEY", "").strip()


def robots_txt(*, sitemap_url: str | None = None) -> str:
    sitemap = sitemap_url or f"{ui_site_url()}/sitemap.xml"
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/files/",
        "Disallow: /api/merge/",
        "Disallow: /api/batch/",
        "",
        f"Sitemap: {sitemap}",
    ]
    return "\n".join(lines) + "\n"


def sitemap_xml(
    *,
    base_url: str | None = None,
    include_api_docs: bool = False,
    api_base: str | None = None,
    base_path: str | None = None,
) -> str:
    full = (base_url or ui_site_url()).rstrip("/")
    origin, url_prefix = _split_origin(full)
    path_prefix = url_prefix if base_path is None else base_path.rstrip("/")
    docs_origin = (api_base or api_origin()).rstrip("/")
    lastmod = sitemap_lastmod()

    entries: list[tuple[str, str, str]] = [
        (origin + canonical_path("dashboard", base_path=path_prefix), "weekly", "1.0"),
    ]
    for slug, _title, _desc in SPA_ROUTES:
        if slug == "dashboard":
            continue
        changefreq, priority = _SITEMAP_META.get(slug, ("monthly", "0.7"))
        entries.append((
            origin + canonical_path(slug, base_path=path_prefix),
            changefreq,
            priority,
        ))
    if include_api_docs:
        for path, _title, _desc in API_DOC_PATHS:
            entries.append((docs_origin + path, "monthly", "0.5"))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, changefreq, priority in entries:
        parts.extend([
            "  <url>",
            f"    <loc>{escape(loc)}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ])
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


def json_ld_webapp(*, base_url: str | None = None) -> dict:
    origin = (base_url or ui_site_url()).rstrip("/")
    data: dict = {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": SITE_NAME,
        "alternateName": "CoH UCS Toolkit",
        "description": SITE_DESCRIPTION,
        "url": origin + "/",
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Any",
        "browserRequirements": "Requires JavaScript",
        "softwareVersion": "1.0.0",
        "isAccessibleForFree": True,
        "license": "https://opensource.org/licenses/MIT",
        "codeRepository": GITHUB_REPO,
        "screenshot": og_image_url(origin),
        "featureList": [
            "UCS file upload and validation",
            "Duplicate and missing ID detection",
            "Two-file comparison and diff",
            "Merge wizard with placeholder support",
            "PO and TMX export",
            "REST API with OpenAPI docs",
        ],
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
        },
    }
    if TWITTER_HANDLE:
        data["creator"] = {"@type": "Organization", "name": SITE_NAME}
    return data


def json_ld_website(*, base_url: str | None = None) -> dict:
    full = (base_url or ui_site_url()).rstrip("/")
    origin, path_prefix = _split_origin(full)
    search_path = canonical_path("search", base_path=path_prefix)
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "alternateName": "CoH UCS Toolkit",
        "description": SITE_DESCRIPTION,
        "url": origin + canonical_path("dashboard", base_path=path_prefix),
        "inLanguage": "en",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": origin + search_path + "?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def json_ld_organization(*, base_url: str | None = None) -> dict:
    origin = (base_url or ui_site_url()).rstrip("/")
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": origin + "/",
        "logo": og_image_url(origin),
        "sameAs": [GITHUB_REPO],
    }


def json_ld_breadcrumb(
    slug: str,
    *,
    base_url: str | None = None,
    title: str | None = None,
) -> dict:
    full = (base_url or ui_site_url()).rstrip("/")
    origin, path_prefix = _split_origin(full)
    page_title = title or next((t for s, t, _ in SPA_ROUTES if s == slug), slug)
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Dashboard",
                "item": origin + canonical_path("dashboard", base_path=path_prefix),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": page_title,
                "item": origin + canonical_path(slug, base_path=path_prefix),
            },
        ],
    }


def json_ld_faq_page(*, base_url: str | None = None) -> dict:
    full = (base_url or ui_site_url()).rstrip("/")
    origin, path_prefix = _split_origin(full)
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in ABOUT_FAQ
        ],
        "url": origin + canonical_path("about", base_path=path_prefix),
    }


def _verification_meta_tags() -> str:
    tags = []
    google = os.environ.get("UCS_GOOGLE_SITE_VERIFICATION", DEFAULT_GOOGLE_SITE_VERIFICATION).strip()
    bing = os.environ.get("UCS_BING_SITE_VERIFICATION", "").strip()
    if google:
        tags.append(f'<meta name="google-site-verification" content="{escape(google)}">')
    if bing:
        tags.append(f'<meta name="msvalidate.01" content="{escape(bing)}">')
    return "\n".join(tags)


def render_head_meta(*, base_url: str | None = None) -> str:
    origin = (base_url or ui_site_url()).rstrip("/")
    title = page_title_suffix()
    img = og_image_url(origin)
    return f"""<title>{escape(title)}</title>
<meta name="description" content="{escape(SITE_DESCRIPTION)}">
<meta name="keywords" content="{escape(SITE_KEYWORDS)}">
<meta name="author" content="{escape(SITE_NAME)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta name="application-name" content="{escape(SITE_NAME)}">

<link rel="canonical" href="{escape(origin)}/">
<link rel="icon" href="/static/icons/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/static/icons/icon-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png" sizes="180x180">
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#1a3a2a">
<meta name="color-scheme" content="dark">

<meta property="og:type" content="website">
<meta property="og:site_name" content="{escape(SITE_NAME)}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(SITE_DESCRIPTION)}">
<meta property="og:url" content="{escape(origin)}/">
<meta property="og:image" content="{escape(img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{escape(SITE_NAME)} — Company of Heroes localization command console">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(title)}">
<meta name="twitter:description" content="{escape(SITE_DESCRIPTION)}">
<meta name="twitter:image" content="{escape(img)}">
<meta name="twitter:image:alt" content="{escape(SITE_NAME)} — Company of Heroes localization command console">
{_verification_meta_tags()}"""


def render_json_ld_script(*, base_url: str | None = None) -> str:
    graph = [
        json_ld_webapp(base_url=base_url),
        json_ld_website(base_url=base_url),
        json_ld_organization(base_url=base_url),
    ]
    payload = json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=2)
    return f'<script type="application/ld+json" id="seo-root-ld">\n{payload}\n</script>'


def render_route_seo_script() -> str:
    payload = json.dumps(route_seo_map(), ensure_ascii=False)
    faq = [{"question": q, "answer": a} for q, a in ABOUT_FAQ]
    site = json.dumps(SITE_NAME, ensure_ascii=False)
    return (
        f"<script>window.ROUTE_SEO={payload};"
        f"window.ABOUT_FAQ={json.dumps(faq, ensure_ascii=False)};"
        f"window.SITE_NAME={site};</script>"
    )


def render_noscript_fallback(*, base_path: str = "") -> str:
    prefix = base_path.rstrip("/")
    links = []
    for slug, title, desc in SPA_ROUTES:
        if slug == "dashboard":
            href = f"{prefix}/" if prefix else "/"
        elif prefix:
            href = f"{prefix}/{slug}"
        else:
            href = f"/{slug}"
        links.append(
            f'      <li><a href="{escape(href)}">{escape(title)}</a> — {escape(desc)}</li>'
        )
    items = "\n".join(links)
    return f"""  <noscript>
    <div class="noscript-fallback">
      <h2>{escape(SITE_NAME)}</h2>
      <p>{escape(SITE_DESCRIPTION)}</p>
      <p>This console requires JavaScript. Enable it to upload and analyze <code>.ucs</code> files, or browse the sections below.</p>
      <ul>
{items}
      </ul>
      <p><a href="{escape(GITHUB_REPO)}">Source on GitHub</a> · REST API docs on <a href="{escape(api_origin())}/docs">Fly.io</a></p>
    </div>
  </noscript>"""


def inject_index_html(html: str, *, base_url: str | None = None, base_path: str = "") -> str:
    """Replace SEO markers in index.html with generated metadata."""
    head_block = "\n".join([
        render_head_meta(base_url=base_url),
        render_json_ld_script(base_url=base_url),
        render_route_seo_script(),
    ])
    if SEO_HEAD_START in html:
        html = re.sub(
            rf"{re.escape(SEO_HEAD_START)}.*?{re.escape(SEO_HEAD_END)}",
            f"{SEO_HEAD_START}\n{head_block}\n{SEO_HEAD_END}",
            html,
            count=1,
            flags=re.DOTALL,
        )
    noscript = render_noscript_fallback(base_path=base_path)
    if SEO_NOSCRIPT_START in html:
        html = re.sub(
            rf"{re.escape(SEO_NOSCRIPT_START)}.*?{re.escape(SEO_NOSCRIPT_END)}",
            f"{SEO_NOSCRIPT_START}\n{noscript}\n{SEO_NOSCRIPT_END}",
            html,
            count=1,
            flags=re.DOTALL,
        )
    return html


def is_spa_path(path: str) -> bool:
    """Return True if *path* should serve the SPA shell (path-based routing)."""
    path = path.strip("/")
    if not path:
        return True
    slug = path.split("/")[0]
    if slug in _SPA_RESERVED_PREFIXES:
        return False
    return slug in SPA_SLUGS
