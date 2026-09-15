"""Contracts for deterministic, checksum-bound release assets."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from tools.release.artifact import __main__ as commands
from tools.release.artifact import bundle as asset_command
from tools.release.artifact import format as assets

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "defect", ["missing-distribution", "missing-record", "malformed-record", "missing-provenance"]
)
def test_normalization_requires_complete_installed_metadata(tmp_path, defect):
    if defect != "missing-distribution":
        _installed_distribution(tmp_path, "isolated")
        metadata = next(tmp_path.glob("*.dist-info"))
        if defect == "missing-record":
            (metadata / "RECORD").unlink()
        elif defect == "malformed-record":
            (metadata / "RECORD").write_text("invalid\n")
        else:
            (metadata / "direct_url.json").unlink()
    with pytest.raises(RuntimeError, match=r"distribution|provenance"):
        asset_command.normalize(tmp_path)


def test_bundle_rejects_directory_symlink_cycles(tmp_path):
    (tmp_path / "cycle").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SystemExit, match="symlink cycle"):
        asset_command.bundle_files(tmp_path)


@pytest.mark.parametrize("defect", ["occupied-output", "file-input", "missing-executable"])
def test_pack_rejects_invalid_roots_before_writing(tmp_path, defect):
    bundle = tmp_path / "bundle"
    output = tmp_path / "output"
    if defect == "file-input":
        bundle.touch()
    else:
        bundle.mkdir()
    if defect == "occupied-output":
        output.mkdir()
        (output / "preserved").write_bytes(b"owned")
    with pytest.raises(SystemExit):
        asset_command.pack(bundle=bundle, platform="linux-x86_64", output=output)
    if defect == "occupied-output":
        assert (output / "preserved").read_bytes() == b"owned"
    else:
        assert not output.exists()


def _installed_distribution(root: Path, provenance: str) -> Path:
    """Create one installed product distribution with local installer metadata."""
    metadata = root / "codex_responses_proxy-2.0.30.dist-info"
    package = root / "codex_responses_proxy"
    metadata.mkdir(parents=True)
    package.mkdir()
    (package / "__init__.py").write_text('__version__ = "2.0.30"\n', encoding="utf-8")
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: codex-responses-proxy\nVersion: 2.0.30\n",
        encoding="utf-8",
    )
    (metadata / "direct_url.json").write_text(
        json.dumps({"url": f"file://{provenance}/product.whl"}), encoding="utf-8"
    )
    (metadata / "uv_cache.json").write_text(
        json.dumps({"timestamp": {"secs_since_epoch": len(provenance)}}),
        encoding="utf-8",
    )
    rows = [
        "codex_responses_proxy/__init__.py,,",
        "codex_responses_proxy-2.0.30.dist-info/METADATA,,",
        "codex_responses_proxy-2.0.30.dist-info/direct_url.json,,",
        "codex_responses_proxy-2.0.30.dist-info/uv_cache.json,,",
        "codex_responses_proxy-2.0.30.dist-info/RECORD,,",
    ]
    (metadata / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root


class BundleContracts:
    """Verify the bundle owner of native release artifacts."""

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

        files = dict(asset_command.bundle_files(bundle))

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
                for path, source in asset_command.bundle_files(bundle)
            }
            archives.append(assets.archive_bytes(files, "2.0.26", "linux-x86_64"))

        assert archives[0] == archives[1]

    def test_native_freeze_input_discards_installer_provenance(self, tmp_path: Path) -> None:
        """Normalize metadata before it can alter the frozen executable."""
        first = _installed_distribution(tmp_path / "github", "/workspace/github")
        second = _installed_distribution(tmp_path / "gitlab", "/builds/gitlab")

        commands.main(("normalize", "--packages", str(first)))
        commands.main(("normalize", "--packages", str(second)))

        def snapshot(root: Path) -> dict[str, bytes]:
            return {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }

        assert snapshot(first) == snapshot(second)
        assert not any(
            path.name in {"direct_url.json", "uv_cache.json"} for path in first.rglob("*")
        )

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
                    "artifact",
                    "pack",
                    "--bundle",
                    str(bundle),
                    "--platform",
                    "linux-x86_64",
                    "--output",
                    str(output),
                ],
            )
            commands.main()
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

        asset_command.pack(bundle=bundle, platform="macos-arm64", output=output)

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
            asset_command.pack(
                bundle=bundle,
                platform="macos-arm64",
                output=tmp_path / "release",
            )
