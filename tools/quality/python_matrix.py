"""Project the supported Python lines into GitHub Actions outputs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cyclopts import App


def write(*, versions: Path, output: Path) -> None:
    """Write matrix, floor, and latest outputs from the repository SSOT."""

    values = versions.read_text(encoding="utf-8").splitlines()
    if not values or len(values) != len(set(values)) or output.is_symlink():
        raise ValueError("supported Python matrix is unavailable or invalid")
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"value={json.dumps(values)}\n")
        stream.write(f"floor={values[0]}\n")
        stream.write(f"latest={values[-1]}\n")


def _command(
    *,
    versions: Path = Path(".python-versions"),
    output: Path | None = None,
) -> None:
    """Project the matrix to an explicit or GitHub-provided output path."""

    configured = os.environ.get("GITHUB_OUTPUT")
    if output is None and not configured:
        raise SystemExit("GitHub output path is unavailable")
    target = output or Path(configured or "")
    write(versions=versions, output=target)


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run matrix projection through the repository parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
