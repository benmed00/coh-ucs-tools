"""Tests for static i18n JSON parity and build output."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


from tests.conftest import STATIC_DIR

I18N_DIR = STATIC_DIR / "i18n"
REQUIRED_LOCALES = ("en", "fr", "ar")


class I18nStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.en_keys = set(json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8")).keys())

    def test_en_json_valid(self) -> None:
        data = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))
        self.assertIn("nav.dashboard", data)
        self.assertIn("route.dashboard", data)
        self.assertIn("hero.tag_html", data)
        self.assertIn("err.404", data)
        self.assertGreater(len(data), 300)

    def test_faq_keys_present(self) -> None:
        data = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))
        for i in range(6):
            self.assertIn(f"faq.{i}.q", data)
            self.assertIn(f"faq.{i}.a", data)

    def test_locale_parity(self) -> None:
        for loc in REQUIRED_LOCALES:
            path = I18N_DIR / f"{loc}.json"
            self.assertTrue(path.is_file(), f"missing {path}")
            data = json.loads(path.read_text(encoding="utf-8"))
            missing = self.en_keys - set(data.keys())
            extra = set(data.keys()) - self.en_keys
            self.assertFalse(missing, f"{loc} missing keys: {sorted(missing)[:10]}")
            self.assertFalse(extra, f"{loc} extra keys: {sorted(extra)[:10]}")


class BuildStaticUiTests(unittest.TestCase):
    def test_build_includes_card_header_and_i18n(self) -> None:
        from scripts.build.static import build_static, _SW_CACHE

        self.assertEqual(_SW_CACHE, "coh-ucs-v12")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dist"
            build_static(out, "https://coh-ucs-tools.fly.dev", "https://benmed00.github.io/coh-ucs-tools")
            css = (out / "css" / "app.css").read_text(encoding="utf-8")
            motion = (out / "css" / "motion.css").read_text(encoding="utf-8")
            sw = (out / "service-worker.js").read_text(encoding="utf-8")
            self.assertIn(".card-header", css)
            self.assertIn("prefers-reduced-motion", motion)
            self.assertIn("coh-ucs-v12", sw)
            self.assertIn("js/motion.js", sw)
            self.assertIn("js/i18n.js", sw)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("motion.css", index)
            self.assertIn("/coh-ucs-tools/sitemap.xml", index)
            self.assertIn("renderPaneError", (out / "js" / "core.js").read_text(encoding="utf-8"))
            self.assertIn('rel="icon"', index)
            self.assertIn("parseRouteFromHref", (out / "js" / "router.js").read_text(encoding="utf-8"))

    def test_app_js_syntax(self) -> None:
        import subprocess

        js_dir = STATIC_DIR / "js"
        for path in sorted(js_dir.glob("*.js")):
            with self.subTest(path=path.name):
                r = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(r.returncode, 0, f"{path.name}: {r.stderr or r.stdout}")


if __name__ == "__main__":
    unittest.main()
