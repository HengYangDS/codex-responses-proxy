#!/usr/bin/env python3
"""Assemble verified native platform outputs into one release asset set."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

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


def _command(
    *,
    inputs: Annotated[tuple[Path, ...], Parameter(name="--input")] = (),
    output: Path | None = None,
    verify_path: Annotated[Path | None, Parameter(name="--verify")] = None,
) -> None:
    """Assemble or verify one complete release asset set."""

    if verify_path:
        if inputs or output:
            raise SystemExit("--verify cannot be combined with --input or --output")
        digests = verify(verify_path)
        print(f"verified release assets: {len(digests)} files")
        return
    if not inputs or not output:
        raise SystemExit("--input and --output are required when assembling")
    release = assemble(inputs, output)
    print(f"assembled release assets: {len(release)} files")


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run release assembly through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
