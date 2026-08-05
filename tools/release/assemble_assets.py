#!/usr/bin/env python3
"""Assemble verified native platform outputs into one release asset set."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.release import product_assets as assets


def assemble(inputs: tuple[Path, ...], output: Path) -> dict[str, bytes]:
    """Verify and copy one exact asset pair for every supported platform."""

    if output.exists() and any(output.iterdir()):
        raise assets.AssetError("release asset output directory must be empty")
    discovered: dict[str, bytes] = {}
    for root in inputs:
        for path in root.rglob("*"):
            if not path.is_file() or path.name == assets.CHECKSUM_NAME:
                continue
            if path.name in discovered:
                raise assets.AssetError(f"duplicate release asset: {path.name}")
            discovered[path.name] = path.read_bytes()
    version = _version(discovered)
    expected = assets.release_asset_names(
        version, assets.RELEASE_PLATFORMS, require_signature=False
    ) - {assets.CHECKSUM_NAME}
    if set(discovered) != expected:
        raise assets.AssetError("native platform asset set is incomplete or contains unknown files")
    for platform in assets.RELEASE_PLATFORMS:
        assets.verify_platform_archive(
            discovered[assets.archive_name(version, platform)],
            discovered[assets.manifest_name(platform)],
        )
    release = {**discovered, assets.CHECKSUM_NAME: assets.checksums(discovered)}
    output.mkdir(parents=True, exist_ok=True)
    for name, content in release.items():
        (output / name).write_bytes(content)
    return release


def verify(root: Path, *, require_signature: bool = True) -> dict[str, str]:
    """Verify one complete release directory and return its exact digests."""

    files = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
    versions = {
        name.removeprefix("codex-responses-proxy-").removesuffix(f"-{platform}.tar.gz")
        for platform in assets.RELEASE_PLATFORMS
        for name in files
        if name.endswith(f"-{platform}.tar.gz")
    }
    if len(versions) != 1:
        raise assets.AssetError("release directory does not contain one version")
    return assets.release_digests(
        files,
        versions.pop(),
        assets.RELEASE_PLATFORMS,
        require_signature=require_signature,
    )


def _version(discovered: dict[str, bytes]) -> str:
    versions = {
        name.removeprefix("codex-responses-proxy-").removesuffix(f"-{platform}.tar.gz")
        for platform in assets.RELEASE_PLATFORMS
        for name in discovered
        if name.endswith(f"-{platform}.tar.gz")
    }
    if len(versions) != 1:
        raise assets.AssetError("native platform assets do not share one version")
    return versions.pop()


def main() -> None:
    """Assemble the command-line inputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    if arguments.verify:
        if arguments.input or arguments.output:
            parser.error("--verify cannot be combined with --input or --output")
        digests = verify(arguments.verify)
        print(f"verified release assets: {len(digests)} files")
        return
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required when assembling")
    release = assemble(tuple(arguments.input), arguments.output)
    print(f"assembled release assets: {len(release)} files")


if __name__ == "__main__":
    main()
