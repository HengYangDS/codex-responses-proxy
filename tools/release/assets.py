#!/usr/bin/env python3
"""Package one accepted native executable into a manifest-bound release asset."""

from __future__ import annotations

import sys
from pathlib import Path

from cyclopts import App

from tools.release import product_assets as assets

ROOT = Path(__file__).resolve().parents[2]


def _command(*, executable: Path, platform: str, output: Path) -> None:
    """Write one platform archive, machine manifest, and checksum manifest."""

    if output.exists() and any(output.iterdir()):
        raise SystemExit("release asset output directory must be empty")
    executable = executable.resolve(strict=True)
    if not executable.is_file():
        raise SystemExit("native executable must be a regular file")
    version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
    executable_name = (
        "codex-responses-proxy.exe" if executable.suffix == ".exe" else "codex-responses-proxy"
    )
    files = {
        executable_name: assets.ArchiveFile(executable.read_bytes(), 0o755),
        "providers.toml": (ROOT / "src/codex_responses_proxy/providers/manifest.toml").read_bytes(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
    }
    archive_name = assets.archive_name(version, platform)
    archive = assets.archive_bytes(files, version, platform)
    manifest_name = assets.manifest_name(platform)
    manifest = assets.asset_manifest(
        version=version,
        platform=platform,
        archive_name=archive_name,
        archive=archive,
        files=files,
    )
    release_files = {archive_name: archive, manifest_name: manifest}
    checksums = assets.checksums(release_files)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in {**release_files, assets.CHECKSUM_NAME: checksums}.items():
        (output / name).write_bytes(content)
    assets.release_digests(
        {**release_files, assets.CHECKSUM_NAME: checksums},
        version,
        (platform,),
        require_signature=False,
    )
    print(f"release assets: {archive_name} {manifest_name} {assets.CHECKSUM_NAME} OK")


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run asset assembly through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
