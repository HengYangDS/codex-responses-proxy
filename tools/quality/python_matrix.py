"""Project the supported Python lines into GitHub Actions outputs."""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

from cyclopts import App


def write(*, versions: Path, release: Path, metadata: Path, output: Path) -> None:
    """Write Python and native-runtime outputs from repository SSOTs."""

    values = versions.read_text(encoding="utf-8").splitlines()
    if not values or len(values) != len(set(values)) or output.is_symlink():
        raise ValueError("supported Python matrix is unavailable or invalid")
    release_version = release.read_text(encoding="utf-8").strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", release_version) is None:
        raise ValueError("native release Python is unavailable or invalid")
    project = tomllib.loads(metadata.read_text(encoding="utf-8"))
    image = project["tool"]["codex-responses-proxy"]["linux-release-image"]
    if (
        not isinstance(image, str)
        or f"python:{release_version}-" not in image
        or "@sha256:" not in image
    ):
        raise ValueError("Linux release runtime is unavailable or mutable")
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"value={json.dumps(values)}\n")
        stream.write(f"floor={values[0]}\n")
        stream.write(f"latest={values[-1]}\n")
        stream.write(f"release={release_version}\n")
        stream.write(f"linux-release-image={image}\n")


def _command(
    *,
    versions: Path = Path(".python-versions"),
    release: Path = Path(".python-release"),
    metadata: Path = Path("pyproject.toml"),
    output: Path | None = None,
) -> None:
    """Project the matrix to an explicit or GitHub-provided output path."""

    configured = os.environ.get("GITHUB_OUTPUT")
    if output is None and not configured:
        raise SystemExit("GitHub output path is unavailable")
    target = output or Path(configured or "")
    write(versions=versions, release=release, metadata=metadata, output=target)


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run matrix projection through the repository parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
