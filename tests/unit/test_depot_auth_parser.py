"""Wave 4: DepotDownloader, auth, chunked parser, IT/PL locale specs."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


from coh_ucs_tools.core.parser import BOM_LE, iter_ucs_lines_chunked, parse_file, parse_file_chunked, scan_file_stats
from coh_ucs_tools.tools.depot import DEPOT_SPECS, download_depot_locale, list_depot_specs, run_locale_build
from coh_ucs_tools.web.auth import (
    authenticate_local,
    create_session_token,
    is_public_path,
    verify_session_token,
)


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class ChunkedParserTests(unittest.TestCase):
    def test_chunked_matches_small_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.ucs"
            path.write_bytes(ucs_bytes({i: f"v{i}" for i in range(1, 200)}))
            small = parse_file(path)
            # Force chunked path regardless of size
            chunked = parse_file_chunked(path)
            self.assertEqual(small.entries, chunked.entries)

    def test_large_file_uses_chunked_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.ucs"
            # ~600 KiB — above 512 KiB threshold
            entries = {i: "x" * 80 for i in range(1, 4000)}
            path.write_bytes(ucs_bytes(entries))
            stats = scan_file_stats(path)
            self.assertTrue(stats.get("chunked"))
            self.assertEqual(stats["keys"], len(entries))
            doc = parse_file(path)
            self.assertEqual(len(doc.entries), len(entries))

    def test_iter_lines_chunked_splits_crlf_across_chunks(self) -> None:
        raw = ucs_bytes({1: "a", 2: "bb", 3: "ccc"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "split.ucs"
            path.write_bytes(raw)
            lines = list(iter_ucs_lines_chunked(path))
            self.assertEqual(lines, ["1\ta", "2\tbb", "3\tccc"])


class DepotDownloaderTests(unittest.TestCase):
    def test_list_specs_includes_italian_polish(self) -> None:
        langs = {s["language"] for s in list_depot_specs()}
        self.assertIn("italian", langs)
        self.assertIn("polish", langs)

    @patch("coh_ucs_tools.tools.depot.subprocess.run")
    @patch("coh_ucs_tools.tools.depot.find_depotdownloader")
    def test_download_copies_largest_ucs(self, mock_find: MagicMock, mock_run: MagicMock) -> None:
        mock_find.return_value = Path("DepotDownloader.exe")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            downloads = root / "downloads"
            work = root / "work"
            work.mkdir()
            ucs = work / "CoH" / "Engine" / "Locale" / "French" / "RelicCOH.French.ucs"
            ucs.parent.mkdir(parents=True)
            ucs.write_bytes(ucs_bytes({1: "un", 2: "deux"}))
            os.environ["STEAM_USERNAME"] = "u"
            os.environ["STEAM_PASSWORD"] = "p"
            try:
                with patch("coh_ucs_tools.tools.depot.DOWNLOADS_DIR", downloads):
                    result = download_depot_locale("french", output_dir=work)
            finally:
                os.environ.pop("STEAM_USERNAME", None)
                os.environ.pop("STEAM_PASSWORD", None)
            self.assertTrue(result.get("success"))
            dest = Path(result["dest"])
            self.assertTrue(dest.is_file())
            doc = parse_file(dest)
            self.assertEqual(doc.entries[1], "un")

    def test_run_locale_build_no_script_for_english(self) -> None:
        out = run_locale_build("english")
        self.assertFalse(out["built"])


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = {
            k: os.environ.pop(k, None)
            for k in ("UCS_API_KEY", "UCS_ADMIN_PASSWORD", "UCS_SESSION_SECRET", "UCS_ADMIN_USER")
        }

    def tearDown(self) -> None:
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_session_token_roundtrip(self) -> None:
        os.environ["UCS_SESSION_SECRET"] = "test-secret"
        token = create_session_token("alice")
        payload = verify_session_token(token)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["sub"], "alice")

    def test_local_login(self) -> None:
        os.environ["UCS_ADMIN_USER"] = "admin"
        os.environ["UCS_ADMIN_PASSWORD"] = "pass"
        user = authenticate_local("admin", "pass")
        self.assertIsNotNone(user)
        self.assertIsNone(authenticate_local("admin", "wrong"))

    def test_public_get_when_auth_enabled(self) -> None:
        os.environ["UCS_API_KEY"] = "key"
        self.assertTrue(is_public_path("/api/health", "GET"))
        self.assertTrue(is_public_path("/api/files", "GET"))
        self.assertFalse(is_public_path("/api/files", "POST"))


class AuthWebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")
        os.environ["UCS_SESSION_SECRET"] = "web-test-secret"
        os.environ["UCS_ADMIN_USER"] = "admin"
        os.environ["UCS_ADMIN_PASSWORD"] = "secret"

        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        for k in ("UCS_WEBAPP_UPLOADS", "UCS_SESSION_SECRET", "UCS_ADMIN_USER", "UCS_ADMIN_PASSWORD"):
            os.environ.pop(k, None)
        cls._tmp.cleanup()

    def test_auth_status_and_login(self) -> None:
        res = self.client.get("/api/auth/status")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["auth_enabled"])
        self.assertFalse(res.json()["authenticated"])
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["ok"])
        status = self.client.get("/api/auth/status")
        self.assertTrue(status.json()["authenticated"])

    def test_session_allows_mutation(self) -> None:
        self.client.post("/api/auth/logout")
        denied = self.client.post(
            "/api/bookmarks",
            json={"ids": [1]},
        )
        self.assertEqual(denied.status_code, 401)
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
        token = login.json()["token"]
        ok = self.client.post(
            "/api/bookmarks",
            json={"ids": [1]},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(ok.status_code, 200)


class LocaleBuildModuleTests(unittest.TestCase):
    def test_polish_italian_configs(self) -> None:
        from coh_ucs_tools.locale.builders.polish import CONFIG as pl
        from coh_ucs_tools.locale.builders.italian import CONFIG as it

        self.assertEqual(pl.depot_id, DEPOT_SPECS["polish"].depot_id)
        self.assertEqual(it.depot_id, DEPOT_SPECS["italian"].depot_id)


if __name__ == "__main__":
    unittest.main()
