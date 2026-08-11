"""Contracts for deterministic, checksum-bound release assets."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from tools.release import assets as asset_command
from tools.release import assemble_assets
from tools.release import product_assets as assets
import pytest

ROOT = Path(__file__).resolve().parents[2]


class ReleaseAssetContracts:
    """Keep published bytes portable, reproducible, and exactly enumerable."""

    def test_bundle_rejects_installer_provenance(self, tmp_path: Path) -> None:
        """Exclude checkout paths and installer timestamps from release payloads."""

        bundle = tmp_path / "codex-responses-proxy"
        metadata = bundle / "_internal" / "codex_responses_proxy-2.0.25.dist-info"
        metadata.mkdir(parents=True)
        (bundle / "codex-responses-proxy").write_bytes(b"native")
        (metadata / "direct_url.json").write_text(
            '{"url":"file:///private/build/checkout/product.whl"}', encoding="utf-8"
        )
        (metadata / "uv_cache.json").write_text(
            '{"timestamp":{"secs_since_epoch":1}}', encoding="utf-8"
        )

        files = dict(asset_command._bundle_files(bundle))

        assert not any(path.name in {"direct_url.json", "uv_cache.json"} for path in files)

    def test_distinct_checkout_roots_produce_identical_archives(self, tmp_path: Path) -> None:
        """Prove checkout-local installer provenance cannot perturb release bytes."""

        archives = []
        for index, checkout in enumerate(("gitlab-build", "github-runner")):
            bundle = tmp_path / checkout / "codex-responses-proxy"
            metadata = bundle / "_internal" / "codex_responses_proxy-2.0.26.dist-info"
            metadata.mkdir(parents=True)
            (bundle / "codex-responses-proxy").write_bytes(b"native")
            (metadata / "METADATA").write_bytes(b"Name: codex-responses-proxy\n")
            (metadata / "direct_url.json").write_text(
                f'{{"url":"file://{bundle}/wheelhouse/product.whl"}}', encoding="utf-8"
            )
            (metadata / "uv_cache.json").write_text(
                f'{{"timestamp":{{"secs_since_epoch":{index + 1}}}}}', encoding="utf-8"
            )
            files = {
                path.as_posix(): source.read_bytes()
                for path, source in asset_command._bundle_files(bundle)
            }
            archives.append(assets.archive_bytes(files, "2.0.26", "linux-x86_64"))

        assert archives[0] == archives[1]

    def test_platform_archive_is_reproducible_and_manifest_bound(self) -> None:
        files = {
            "bin/codex-responses-proxy": assets.ArchiveFile(b"native-executable", 0o755),
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
            bundle = root / "codex-responses-proxy"
            executable = bundle / "codex-responses-proxy"
            dependency = bundle / "_internal" / "runtime.dat"
            dependency.parent.mkdir(parents=True)
            executable.write_bytes(b"native-executable")
            dependency.write_bytes(b"frozen-runtime")
            output = root / "release"
            mocker.patch.object(asset_command, "ROOT", ROOT)
            mocker.patch(
                "sys.argv",
                [
                    "assets",
                    "--bundle",
                    str(bundle),
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
            manifest = json.loads(release_files[assets.manifest_name("linux-x86_64")])
            assert set(manifest["files"]) == {
                "LICENSE",
                "bin/_internal/runtime.dat",
                "bin/codex-responses-proxy",
                "providers.toml",
            }
            assets.release_digests(
                release_files,
                (ROOT / "VERSION").read_text(encoding="ascii").strip(),
                ("linux-x86_64",),
                require_signature=False,
            )

    @pytest.mark.skipif(os.name == "nt", reason="models POSIX bundle symlink semantics")
    def test_asset_command_materializes_safe_bundle_symlinks(self, tmp_path: Path, mocker) -> None:
        bundle = tmp_path / "codex-responses-proxy"
        framework = bundle / "_internal" / "Python.framework" / "Versions" / "3.14"
        framework.mkdir(parents=True)
        executable = bundle / "codex-responses-proxy"
        executable.write_bytes(b"native-executable")
        runtime = framework / "Python"
        runtime.write_bytes(b"python-runtime")
        (bundle / "_internal" / "Python").symlink_to("Python.framework/Versions/3.14/Python")
        resources = framework / "Resources"
        resources.mkdir()
        (resources / "Info.plist").write_bytes(b"framework-resources")
        (bundle / "_internal" / "Python.framework" / "Resources").symlink_to(
            "Versions/3.14/Resources"
        )
        output = tmp_path / "release"
        mocker.patch.object(asset_command, "ROOT", ROOT)

        asset_command._command(bundle=bundle, platform="macos-arm64", output=output)

        manifest = json.loads((output / assets.manifest_name("macos-arm64")).read_bytes())
        runtime_digest = hashlib.sha256(b"python-runtime").hexdigest()
        assert manifest["files"]["bin/_internal/Python"] == runtime_digest
        assert manifest["files"]["bin/_internal/Python.framework/Versions/3.14/Python"] == (
            runtime_digest
        )
        assert manifest["files"]["bin/_internal/Python.framework/Resources/Info.plist"] == (
            hashlib.sha256(b"framework-resources").hexdigest()
        )

    def test_bundle_files_uses_platform_canonical_path_identity(self, mocker) -> None:
        bundle = Path("C:/Product/Proxy")
        member = Path("c:/product/proxy/_internal/runtime.dat")
        commonpath = os.path.commonpath
        mocker.patch("os.path.normcase", lambda value: value.casefold().replace("\\", "/"))
        mocker.patch(
            "os.path.commonpath",
            lambda paths: (
                "c:\\product\\proxy"
                if tuple(paths) == ("c:/product/proxy", "c:/product/proxy/_internal/runtime.dat")
                else commonpath(paths)
            ),
        )

        assert asset_command._is_within(bundle, member)

    def test_asset_command_rejects_bundle_symlinks_outside_the_bundle(
        self, tmp_path: Path, mocker
    ) -> None:
        bundle = tmp_path / "codex-responses-proxy"
        bundle.mkdir()
        (bundle / "codex-responses-proxy").write_bytes(b"native-executable")
        outside = tmp_path / "outside"
        outside.write_bytes(b"private")
        (bundle / "escape").symlink_to(outside)
        mocker.patch.object(asset_command, "ROOT", ROOT)

        with pytest.raises(SystemExit, match="escapes"):
            asset_command._command(
                bundle=bundle,
                platform="macos-arm64",
                output=tmp_path / "release",
            )

    def test_checksum_manifest_round_trips_and_rejects_drift(self, subtests) -> None:
        platform = "linux-x86_64"
        files = {"bin/codex-responses-proxy": assets.ArchiveFile(b"native", 0o755)}
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
            files = {f"bin/{executable}": assets.ArchiveFile(platform.encode(), 0o755)}
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

    def test_native_outputs_are_assembled_signed_and_verified_by_one_owner(
        self, tmp_path: Path
    ) -> None:
        inputs: list[Path] = []
        for platform in assets.RELEASE_PLATFORMS:
            root = tmp_path / platform
            root.mkdir()
            executable = (
                "codex-responses-proxy.exe"
                if platform.startswith("windows-")
                else "codex-responses-proxy"
            )
            files = {f"bin/{executable}": assets.ArchiveFile(platform.encode(), 0o755)}
            archive_name = assets.archive_name("1.2.3", platform)
            archive = assets.archive_bytes(files, "1.2.3", platform)
            (root / archive_name).write_bytes(archive)
            (root / assets.manifest_name(platform)).write_bytes(
                assets.asset_manifest(
                    version="1.2.3",
                    platform=platform,
                    archive_name=archive_name,
                    archive=archive,
                    files=files,
                )
            )
            inputs.append(root)
        key = tmp_path / "signing"
        subprocess.run(("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)), check=True)
        public = key.with_suffix(".pub").read_text().strip()
        trust = f'codex-responses-proxy-release namespaces="codex-responses-proxy-release" {public}'

        digests = assemble_assets.assemble_sign_verify(
            inputs=tuple(inputs), output=tmp_path / "release", key=key, trust=trust
        )

        assert set(digests) == assets.release_asset_names("1.2.3", assets.RELEASE_PLATFORMS)
        assert key.is_file()

    def test_asset_command_reads_the_signing_key_from_an_explicit_path(
        self, tmp_path: Path, mocker
    ) -> None:
        key = tmp_path / "signing"
        key.write_text("private key fixture", encoding="utf-8")
        assemble = mocker.patch.object(assemble_assets, "assemble_sign_verify", return_value={})
        mocker.patch.dict(
            os.environ,
            {
                "RELEASE_ASSET_SIGNING_KEY_PATH": str(key),
                "RELEASE_ASSET_TRUST": "trust fixture",
            },
        )

        assemble_assets._command(inputs=(tmp_path,), output=tmp_path / "release", sign=True)

        assemble.assert_called_once_with(
            inputs=(tmp_path,),
            output=tmp_path / "release",
            key=key,
            trust="trust fixture",
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
