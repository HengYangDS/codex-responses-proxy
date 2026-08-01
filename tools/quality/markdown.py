#!/usr/bin/env python3
"""Reject Markdown metadata rows that would collapse in CommonMark renderers."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOT_README = Path(os.environ.get("PROXY_README_FILE", ROOT / "README.md"))
PROJECT_NAME = "Codex Responses Proxy"
PROJECT_PATH = "codex-responses-proxy"


def fail(message: str) -> None:
    """Exit with a stable Markdown presentation diagnostic."""

    raise SystemExit(f"Markdown presentation contract: {message}")


def main() -> None:
    text = ROOT_README.read_text(encoding="utf-8")
    identity = (
        "Licensed under [MIT](LICENSE). Forge coordinates and publication actors are\n"
        "deployment context, not product identity."
    )
    if identity not in text:
        fail("README must separate product identity from Forge deployment context")
    if re.search(
        r"^\*\*GitLab Project Name:\*\*[^\n]*(?<!  )\n\*\*GitLab repository path:\*\*",
        text,
        flags=re.MULTILINE,
    ):
        fail("adjacent project metadata rows would collapse without an explicit structure")
    print("Markdown presentation contract: OK")


if __name__ == "__main__":
    main()
