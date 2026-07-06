"""Wave 6: SGA pack/inject, game profile upload, patch chain, depot verification."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


from coh_ucs_tools.core.parser import BOM_LE, parse_file, parse_text
from coh_ucs_tools.analysis.patch_chain import build_patch_chain
from coh_ucs_tools.io.sga import extract_file, pack_sga, read_sga, repack_sga
from coh_ucs_tools.tools.depot import DEPOT_SPECS, list_depot_specs


def ucs_bytes(entries: dict[int, str]) -> bytes:
    text = "".join(f"{k}\t{v}\r\n" for k, v in entries.items())
    return BOM_LE + text.encode("utf-16-le")


class SgaPackTests(unittest.TestCase):
    def test_pack_and_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.sga"
            payload = {1: "hello", 2: "world"}
            pack_sga(out, {
                "Locale/English/test.ucs": ucs_bytes(payload),
                "Data/readme.txt": b"mod",
            })
            arch = read_sga(out)
            self.assertEqual(len(arch.files), 2)
            data, _ = extract_file(out, "Locale/English/test.ucs")
            doc = parse_file(Path(tmp) / "x.ucs") if False else None
            from coh_ucs_tools.core.parser import parse_bytes
            doc = parse_bytes(data)
            self.assertEqual(doc.entries[1], "hello")

    def test_repack_replaces_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "base.sga"
            pack_sga(out, {"Locale/English/a.ucs": ucs_bytes({1: "old"})})
            new_ucs = ucs_bytes({1: "new", 2: "extra"})
            patched = Path(tmp) / "patched.sga"
            repack_sga(out, {"Locale/English/a.ucs": new_ucs}, patched)
            data, _ = extract_file(patched, "Locale/English/a.ucs")
            from coh_ucs_tools.core.parser import parse_bytes
            doc = parse_bytes(data)
            self.assertEqual(doc.entries[1], "new")
            self.assertEqual(doc.entries[2], "extra")


class PatchChainTests(unittest.TestCase):
    def test_chain_counts_deltas(self) -> None:
        thq = parse_text("1\tone\r\n2\ttwo\r\n")
        nsv = parse_text("1\tone\r\n2\tTWO\r\n3\tthree\r\n")
        result = build_patch_chain({
            "thq-retail-english": thq,
            "nsv-english": nsv,
        })
        steps = {s["id"]: s for s in result["chain"]}
        self.assertEqual(steps["nsv-english"]["added"], 1)
        self.assertEqual(steps["nsv-english"]["changed"], 1)


class DepotVerificationTests(unittest.TestCase):
    def test_italian_polish_verified(self) -> None:
        specs = {s["language"]: s for s in list_depot_specs()}
        self.assertTrue(specs["italian"]["depot_verified"])
        self.assertTrue(specs["polish"]["depot_verified"])
        self.assertEqual(DEPOT_SPECS["italian"].depot_id, 4567)
        self.assertEqual(DEPOT_SPECS["polish"].depot_id, 4568)


class UploadProfileWebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["UCS_WEBAPP_UPLOADS"] = str(Path(cls._tmp.name) / "uploads")

        from fastapi.testclient import TestClient
        from coh_ucs_tools.web.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        os.environ.pop("UCS_WEBAPP_UPLOADS", None)
        cls._tmp.cleanup()

    def test_upload_returns_game_profile(self) -> None:
        res = self.client.post(
            "/api/files",
            files={"file": ("t.ucs", ucs_bytes({1: "a", 559200: "x"}), "application/octet-stream")},
            params={"game_profile": "coh1"},
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertIn("game_profile", body)
        self.assertEqual(body["game_profile"]["best_match"], "coh1")

    def test_patch_chain_endpoint(self) -> None:
        res = self.client.get("/api/versions/patch-chain")
        self.assertEqual(res.status_code, 200)
        self.assertIn("chain", res.json())


if __name__ == "__main__":
    unittest.main()
