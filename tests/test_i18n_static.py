"""Tests for static i18n JSON parity and build output."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

I18N_DIR = Path(__file__).resolve().parent.parent / "webapp" / "static" / "i18n"
REQUIRED_LOCALES = ("en", "fr", "ar")


class I18nStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.en_keys = set(json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8")).keys())

    def test_en_json_valid(self) -> None:
        data = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))
        self.assertIn("nav.dashboard", data)
        self.assertIn("route.dashboard", data)
        self.assertGreater(len(data), 50)

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
        from scripts.build_static import build_static, _SW_CACHE

        self.assertEqual(_SW_CACHE, "coh-ucs-v6")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dist"
            build_static(out, "https://coh-ucs-tools.fly.dev", "https://benmed00.github.io/coh-ucs-tools")
            css = (out / "css" / "app.css").read_text(encoding="utf-8")
            sw = (out / "service-worker.js").read_text(encoding="utf-8")
            self.assertIn(".card-header", css)
            self.assertIn("coh-ucs-v6", sw)
            self.assertIn("./js/i18n.js", sw)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("./sitemap.xml", index)
            self.assertIn("initSpaNav", (out / "js" / "router.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
