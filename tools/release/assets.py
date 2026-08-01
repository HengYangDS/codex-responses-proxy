#!/usr/bin/env python3
"""Build deterministic release assets from the exact checked-out Git tree."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.release import assets


def tracked_files() -> dict[str, bytes]:
    """Read release inputs from immutable HEAD blobs, never the worktree stage."""

    paths = subprocess.run(
        ("git", "ls-tree", "-r", "--name-only", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return {
        path: subprocess.run(
            ("git", "show", f"HEAD:{path}"), cwd=ROOT, check=True, capture_output=True
        ).stdout
        for path in paths
    }


def main() -> None:
    """Write the exact archive and checksum manifest to an empty directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists() and any(arguments.output.iterdir()):
        raise SystemExit("release asset output directory must be empty")
    arguments.output.mkdir(parents=True, exist_ok=True)
    files = tracked_files()
    try:
        version = files["VERSION"].decode("ascii").strip()
    except (KeyError, UnicodeDecodeError) as error:
        raise SystemExit("HEAD has no valid ASCII VERSION") from error
    name = assets.ARCHIVE_NAME.format(version=version)
    archive = assets.archive_bytes(files, version)
    manifest = assets.checksums({name: archive})
    (arguments.output / name).write_bytes(archive)
    (arguments.output / assets.CHECKSUM_NAME).write_bytes(manifest)
    assets.verify({name: archive}, manifest)
    print(f"release assets: {name} {assets.CHECKSUM_NAME} OK")


if __name__ == "__main__":
    main()
