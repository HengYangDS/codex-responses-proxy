#!/usr/bin/env python3
"""Package one accepted native executable into a manifest-bound release asset."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.release import product_assets as assets

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Write one platform archive, machine manifest, and checksum manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output
    if output.exists() and any(output.iterdir()):
        raise SystemExit("release asset output directory must be empty")
    executable = arguments.executable.resolve(strict=True)
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
    archive_name = assets.archive_name(version, arguments.platform)
    archive = assets.archive_bytes(files, version, arguments.platform)
    manifest_name = assets.manifest_name(arguments.platform)
    manifest = assets.asset_manifest(
        version=version,
        platform=arguments.platform,
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
        (arguments.platform,),
        require_signature=False,
    )
    print(f"release assets: {archive_name} {manifest_name} {assets.CHECKSUM_NAME} OK")


if __name__ == "__main__":
    main()
