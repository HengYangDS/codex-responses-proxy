#!/usr/bin/env python3
"""Contracts for deterministic, checksum-bound release assets."""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.release import assets


class ReleaseAssetContracts(unittest.TestCase):
    """Keep published bytes portable, reproducible, and exactly enumerable."""

    def test_archive_is_reproducible_normalized_and_prefixed(self) -> None:
        files = {"README.md": b"hello\n", "tools/run.sh": b"#!/bin/sh\ntrue\n"}
        first = assets.archive_bytes(files, "1.2.3")
        second = assets.archive_bytes(dict(reversed(tuple(files.items()))), "1.2.3")
        self.assertEqual(first, second)
        with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as archive:
            members = archive.getmembers()
        self.assertEqual(
            [member.name for member in members],
            [
                "codex-responses-proxy-1.2.3/README.md",
                "codex-responses-proxy-1.2.3/tools/run.sh",
            ],
        )
        self.assertTrue(all(member.mtime == member.uid == member.gid == 0 for member in members))
        self.assertEqual([member.mode for member in members], [0o644, 0o755])

    def test_checksum_manifest_round_trips_and_rejects_drift(self) -> None:
        payload = {"codex-responses-proxy-1.2.3.tar.gz": b"archive"}
        manifest = assets.checksums(payload)
        expected = hashlib.sha256(b"archive").hexdigest()
        self.assertEqual(assets.verify(payload, manifest), {next(iter(payload)): expected})
        release_files = {**payload, assets.CHECKSUM_NAME: manifest}
        self.assertEqual(
            set(assets.release_digests(release_files, "1.2.3")),
            {next(iter(payload)), assets.CHECKSUM_NAME},
        )
        for changed, checksum in (({"wrong": b"archive"}, manifest), (payload, b"bad\n")):
            with (
                self.subTest(changed=changed, checksum=checksum),
                self.assertRaises(assets.AssetError),
            ):
                assets.verify(changed, checksum)
        with self.assertRaises(assets.AssetError):
            assets.release_digests({**release_files, "unexpected": b"x"}, "1.2.3")

    def test_invalid_paths_and_manifests_fail_closed(self) -> None:
        with self.assertRaises(assets.AssetError):
            assets.checksums({})
        for path in ("../escape", "..\\escape", "/absolute", "C:\\absolute"):
            with self.subTest(path=path), self.assertRaises(assets.AssetError):
                assets.archive_bytes({path: b"x"}, "1.2.3")
        for manifest in (
            b"",
            b"\xff",
            b"not-a-digest  asset\n",
            b"0" * 64 + b"  ../escape\n",
            b"0" * 64 + b"  a\n" + b"1" * 64 + b"  a\n",
        ):
            with self.subTest(manifest=manifest), self.assertRaises(assets.AssetError):
                assets.parse_checksums(manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
