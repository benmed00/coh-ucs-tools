"""Tests for SEO metadata, sitemap, robots.txt, path routing, and static build."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


from tests.conftest import STATIC_DIR


class SeoModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("UCS_SITE_URL", None)
        os.environ.pop("UCS_API_ORIGIN", None)

    def test_site_url_default(self) -> None:
        from coh_ucs_tools.web.seo import ui_site_url

        self.assertEqual(ui_site_url(), "https://benmed00.github.io/coh-ucs-tools")

    def test_sitemap_path_based_ui_only(self) -> None:
        from coh_ucs_tools.web.seo import sitemap_xml

        xml = sitemap_xml(include_api_docs=False)
        self.assertIn("https://benmed00.github.io/coh-ucs-tools/upload</loc>", xml)
        self.assertNotIn("/#/upload", xml)
        self.assertNotIn("/docs</loc>", xml)

    def test_sitemap_with_api_docs_uses_fly_origin(self) -> None:
        from coh_ucs_tools.web.seo import sitemap_xml

        xml = sitemap_xml(include_api_docs=True)
        self.assertIn("https://coh-ucs-tools.fly.dev/docs</loc>", xml)
        self.assertIn("https://benmed00.github.io/coh-ucs-tools/upload</loc>", xml)

    def test_is_spa_path(self) -> None:
        from coh_ucs_tools.web.seo import is_spa_path

        self.assertTrue(is_spa_path(""))
        self.assertTrue(is_spa_path("upload"))
        self.assertTrue(is_spa_path("merge-wizard"))
        self.assertFalse(is_spa_path("api/health"))
        self.assertFalse(is_spa_path("static/js/app.js"))

    def test_about_route_has_static_faq_schema(self) -> None:
        from coh_ucs_tools.web.seo import inject_index_html

        raw = (STATIC_DIR / "index.html").read_text(
            encoding="utf-8"
        )
        html = inject_index_html(raw, route_slug="about")
        self.assertIn('id="seo-faq-ld"', html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn("about-prerender", html)
        self.assertIn('class="faq-item"', html)
        self.assertIn("About — CoH UCS Tools", html)
        self.assertIn('rel="canonical" href="https://benmed00.github.io/coh-ucs-tools/about"', html)

    def test_upload_route_has_breadcrumb_schema(self) -> None:
        from coh_ucs_tools.web.seo import inject_index_html

        raw = (STATIC_DIR / "index.html").read_text(
            encoding="utf-8"
        )
        html = inject_index_html(raw, route_slug="upload")
        self.assertIn('id="seo-breadcrumb-ld"', html)
        self.assertIn("Upload &amp; Analyze — CoH UCS Tools", html)
        self.assertNotIn('id="seo-faq-ld"', html)

    def test_inject_index_html(self) -> None:
        from coh_ucs_tools.web.seo import inject_index_html

        raw = (STATIC_DIR / "index.html").read_text(
            encoding="utf-8"
        )
        html = inject_index_html(raw)
        self.assertIn('property="og:title"', html)
        self.assertIn("window.ROUTE_SEO=", html)
        self.assertIn("window.SITE_NAME=", html)
        self.assertIn("<noscript>", html)
        self.assertIn("og-image.png", html)

    def test_route_seo_map_covers_all_slugs(self) -> None:
        from coh_ucs_tools.web.seo import SPA_ROUTES, route_seo_map

        seo = route_seo_map()
        self.assertEqual(len(seo), len(SPA_ROUTES))
        self.assertIn("sga", seo)
        self.assertIn("about", seo)

    def test_about_faq_json_ld(self) -> None:
        from coh_ucs_tools.web.seo import json_ld_faq_page

        data = json_ld_faq_page()
        self.assertEqual(data["@type"], "FAQPage")
        self.assertGreaterEqual(len(data["mainEntity"]), 3)
        self.assertIn("/about", data["url"])

    def test_verification_meta_when_env_set(self) -> None:
        os.environ["UCS_GOOGLE_SITE_VERIFICATION"] = "test-google"
        os.environ["UCS_BING_SITE_VERIFICATION"] = "test-bing"
        from coh_ucs_tools.web.seo import render_head_meta

        html = render_head_meta()
        self.assertIn('name="google-site-verification"', html)
        self.assertIn("test-google", html)
        self.assertIn('name="msvalidate.01"', html)
        os.environ.pop("UCS_GOOGLE_SITE_VERIFICATION")
        os.environ.pop("UCS_BING_SITE_VERIFICATION")

    def test_verification_meta_default_google(self) -> None:
        os.environ.pop("UCS_GOOGLE_SITE_VERIFICATION", None)
        from coh_ucs_tools.web.seo import DEFAULT_GOOGLE_SITE_VERIFICATION, render_head_meta

        html = render_head_meta()
        self.assertIn(DEFAULT_GOOGLE_SITE_VERIFICATION, html)

    def test_sitemap_includes_about_high_priority(self) -> None:
        from coh_ucs_tools.web.seo import sitemap_xml, ui_site_url

        xml = sitemap_xml(include_api_docs=False)
        about_loc = f"{ui_site_url().rstrip('/')}/about</loc>"
        idx = xml.index(about_loc)
        chunk = xml[idx:idx + 280]
        self.assertIn("<priority>0.9</priority>", chunk)

    def test_sitemap_lastmod_is_iso_date(self) -> None:
        from coh_ucs_tools.web.seo import sitemap_lastmod, sitemap_xml

        lastmod = sitemap_lastmod()
        self.assertRegex(lastmod, r"^\d{4}-\d{2}-\d{2}$")
        xml = sitemap_xml(include_api_docs=False)
        self.assertIn(f"<lastmod>{lastmod}</lastmod>", xml)

    def test_json_ld_graph_includes_website_and_org(self) -> None:
        from coh_ucs_tools.web.seo import json_ld_organization, json_ld_website, render_json_ld_script

        site = json_ld_website()
        self.assertEqual(site["@type"], "WebSite")
        self.assertIn("SearchAction", site["potentialAction"]["@type"])
        org = json_ld_organization()
        self.assertEqual(org["@type"], "Organization")
        script = render_json_ld_script()
        self.assertIn('"@graph"', script)
        self.assertIn("WebApplication", script)
        self.assertIn("WebSite", script)

    def test_json_ld_breadcrumb(self) -> None:
        from coh_ucs_tools.web.seo import json_ld_breadcrumb

        data = json_ld_breadcrumb("upload")
        self.assertEqual(data["@type"], "BreadcrumbList")
        self.assertEqual(len(data["itemListElement"]), 2)
        self.assertIn("/upload", data["itemListElement"][1]["item"])

    def test_indexnow_key_env(self) -> None:
        os.environ["UCS_INDEXNOW_KEY"] = "abc123def456"
        from coh_ucs_tools.web.seo import indexnow_key

        self.assertEqual(indexnow_key(), "abc123def456")
        os.environ.pop("UCS_INDEXNOW_KEY")


class SeoRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        cls.client = TestClient(app)

    def test_spa_path_route_serves_html(self) -> None:
        res = self.client.get("/upload")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("window.ROUTE_SEO=", res.text)
        self.assertIn("window.ABOUT_FAQ=", res.text)
        self.assertIn("<noscript>", res.text)

    def test_about_route_serves_html(self) -> None:
        res = self.client.get("/about")
        self.assertEqual(res.status_code, 200)
        self.assertIn("window.ABOUT_FAQ=", res.text)
        self.assertIn('id="seo-faq-ld"', res.text)
        self.assertIn("about-prerender", res.text)

    def test_google_verification_html_route(self) -> None:
        res = self.client.get("/google34239ced659ea41b.html")
        self.assertEqual(res.status_code, 200)
        self.assertIn("google-site-verification:", res.text)

    def test_index_has_google_verification_meta(self) -> None:
        from coh_ucs_tools.web.seo import DEFAULT_GOOGLE_SITE_VERIFICATION

        res = self.client.get("/")
        self.assertIn(DEFAULT_GOOGLE_SITE_VERIFICATION, res.text)

    def test_unknown_path_404(self) -> None:
        res = self.client.get("/not-a-real-route")
        self.assertEqual(res.status_code, 404)

    def test_index_has_injected_seo(self) -> None:
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("og-image.png", res.text)
        self.assertIn('"@graph"', res.text)
        self.assertIn("github.com/benmed00/coh-ucs-tools", res.text)

    def test_api_routes_noindex(self) -> None:
        res = self.client.get("/api/auth/status")
        self.assertEqual(res.headers.get("x-robots-tag"), "noindex, nofollow")


class IndexNowRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["UCS_INDEXNOW_KEY"] = "test-indexnow-key-001"
        from importlib import reload

        import coh_ucs_tools.web.main as main_mod

        reload(main_mod)
        from fastapi.testclient import TestClient

        cls.client = TestClient(main_mod.app)

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("UCS_INDEXNOW_KEY", None)
        from importlib import reload

        import coh_ucs_tools.web.main as main_mod

        reload(main_mod)

    def test_indexnow_key_route(self) -> None:
        res = self.client.get("/test-indexnow-key-001.txt")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.text.strip(), "test-indexnow-key-001")


class BuildStaticSeoTests(unittest.TestCase):
    def test_build_static_path_routing_assets(self) -> None:
        from scripts.build.static import build_static

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dist"
            build_static(out, "https://coh-ucs-tools.fly.dev", "https://benmed00.github.io/coh-ucs-tools")
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertTrue((out / "404.html").is_file())
            self.assertTrue((out / "google34239ced659ea41b.html").is_file())
            self.assertIn("window.BASE_PATH", (out / "js" / "config.js").read_text(encoding="utf-8"))
            self.assertIn("/coh-ucs-tools", (out / "js" / "config.js").read_text(encoding="utf-8"))
            self.assertIn("<noscript>", index)
            self.assertIn("/coh-ucs-tools/css/fonts.css", index)
            self.assertNotIn("fonts.googleapis.com", index)
            self.assertTrue((out / "_headers").is_file())
            sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn("/coh-ucs-tools/upload</loc>", sitemap)
            self.assertNotIn("/docs</loc>", sitemap)
            about = (out / "about" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="seo-faq-ld"', about)
            self.assertIn("/coh-ucs-tools/css/fonts.css", about)
            upload = (out / "upload" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="seo-breadcrumb-ld"', upload)
            self.assertIn("/coh-ucs-tools/js/config.js", upload)
            self.assertNotIn('id="seo-faq-ld"', upload)


if __name__ == "__main__":
    unittest.main()
