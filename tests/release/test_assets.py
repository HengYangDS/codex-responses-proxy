"""Contracts for deterministic, checksum-bound release assets."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from tools.release import assets as asset_command
from tools.release import assemble_assets
from tools.release import product_assets as assets
import pytest

ROOT = Path(__file__).resolve().parents[2]


class ReleaseAssetContracts:
    """Keep published bytes portable, reproducible, and exactly enumerable."""

    def test_platform_archive_is_reproducible_and_manifest_bound(self) -> None:
        files = {
            "codex-responses-proxy": assets.ArchiveFile(b"native-executable", 0o755),
            "providers.toml": b"version = 1\n",
            "LICENSE": b"MIT\n",
        }
        first = assets.archive_bytes(files, "1.2.3", "linux-x86_64")
        second = assets.archive_bytes(dict(reversed(tuple(files.items()))), "1.2.3", "linux-x86_64")
        assert first == second
        archive_name = assets.archive_name("1.2.3", "linux-x86_64")
        manifest = assets.asset_manifest(
            version="1.2.3",
            platform="linux-x86_64",
            archive_name=archive_name,
            archive=first,
            files=files,
        )
        decoded = json.loads(manifest)
        assert decoded["schema_version"] == 1
        assert decoded["version"] == "1.2.3"
        assert decoded["platform"] == "linux-x86_64"
        assert decoded["archive"] == archive_name
        assert set(decoded["files"]) == set(files)
        assets.verify_platform_archive(first, manifest)
        with pytest.raises(assets.AssetError):
            assets.verify_platform_archive(first + b"drift", manifest)

    def test_asset_command_packages_only_native_runtime_inputs(self, *, mocker) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex-responses-proxy"
            executable.write_bytes(b"native-executable")
            output = root / "release"
            mocker.patch.object(asset_command, "ROOT", ROOT)
            mocker.patch(
                "sys.argv",
                [
                    "assets",
                    "--executable",
                    str(executable),
                    "--platform",
                    "linux-x86_64",
                    "--output",
                    str(output),
                ],
            )
            asset_command.main()
            archive_name = assets.archive_name(
                (ROOT / "VERSION").read_text(encoding="ascii").strip(),
                "linux-x86_64",
            )
            expected = {
                archive_name,
                assets.manifest_name("linux-x86_64"),
                assets.CHECKSUM_NAME,
            }
            assert {path.name for path in output.iterdir()} == expected
            release_files = {path.name: path.read_bytes() for path in output.iterdir()}
            assets.release_digests(
                release_files,
                (ROOT / "VERSION").read_text(encoding="ascii").strip(),
                ("linux-x86_64",),
                require_signature=False,
            )

    def test_checksum_manifest_round_trips_and_rejects_drift(self, subtests) -> None:
        platform = "linux-x86_64"
        files = {"codex-responses-proxy": assets.ArchiveFile(b"native", 0o755)}
        archive_name = assets.archive_name("1.2.3", platform)
        archive = assets.archive_bytes(files, "1.2.3", platform)
        payload = {
            archive_name: archive,
            assets.manifest_name(platform): assets.asset_manifest(
                version="1.2.3",
                platform=platform,
                archive_name=archive_name,
                archive=archive,
                files=files,
            ),
        }
        manifest = assets.checksums(payload)
        expected = hashlib.sha256(archive).hexdigest()
        assert assets.verify(payload, manifest)[archive_name] == expected
        release_files = {**payload, assets.CHECKSUM_NAME: manifest, assets.SIGNATURE_NAME: b"sig"}
        assert set(assets.release_digests(release_files, "1.2.3", ("linux-x86_64",))) == {
            next(iter(payload)),
            assets.manifest_name("linux-x86_64"),
            assets.CHECKSUM_NAME,
            assets.SIGNATURE_NAME,
        }
        for changed, checksum in (({"wrong": b"archive"}, manifest), (payload, b"bad\n")):
            with (
                subtests.test(changed=changed, checksum=checksum),
                pytest.raises(assets.AssetError),
            ):
                assets.verify(changed, checksum)
        with pytest.raises(assets.AssetError):
            assets.release_digests(
                {**release_files, "unexpected": b"x"},
                "1.2.3",
                ("linux-x86_64",),
            )

    def test_native_platform_outputs_assemble_into_one_release(self, tmp_path: Path) -> None:
        inputs: list[Path] = []
        version = "1.2.3"
        for platform in assets.RELEASE_PLATFORMS:
            root = tmp_path / platform
            root.mkdir()
            executable = (
                "codex-responses-proxy.exe"
                if platform.startswith("windows-")
                else "codex-responses-proxy"
            )
            files = {executable: assets.ArchiveFile(platform.encode(), 0o755)}
            archive_name = assets.archive_name(version, platform)
            archive = assets.archive_bytes(files, version, platform)
            (root / archive_name).write_bytes(archive)
            (root / assets.manifest_name(platform)).write_bytes(
                assets.asset_manifest(
                    version=version,
                    platform=platform,
                    archive_name=archive_name,
                    archive=archive,
                    files=files,
                )
            )
            (root / assets.CHECKSUM_NAME).write_bytes(b"ignored platform checksum\n")
            inputs.append(root)
        output = tmp_path / "release"
        release = assemble_assets.assemble(tuple(inputs), output)
        assert set(release) == assets.release_asset_names(
            version, assets.RELEASE_PLATFORMS, require_signature=False
        )
        assets.release_digests(release, version, assets.RELEASE_PLATFORMS, require_signature=False)
        (output / assets.SIGNATURE_NAME).write_bytes(b"signature fixture\n")
        assert set(assemble_assets.verify(output)) == assets.release_asset_names(
            version, assets.RELEASE_PLATFORMS
        )

    def test_invalid_paths_and_manifests_fail_closed(self, subtests) -> None:
        with pytest.raises(assets.AssetError):
            assets.checksums({})
        for path in ("../escape", "..\\escape", "/absolute", "C:\\absolute"):
            with subtests.test(path=path), pytest.raises(assets.AssetError):
                assets.archive_bytes({path: b"x"}, "1.2.3", "linux-x86_64")
        for manifest in (
            b"",
            b"\xff",
            b"not-a-digest  asset\n",
            b"0" * 64 + b"  ../escape\n",
            b"0" * 64 + b"  a\n" + b"1" * 64 + b"  a\n",
        ):
            with subtests.test(manifest=manifest), pytest.raises(assets.AssetError):
                assets.parse_checksums(manifest)
