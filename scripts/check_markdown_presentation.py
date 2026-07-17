#!/usr/bin/env python3
"""Reject Markdown metadata rows that would collapse in CommonMark renderers."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_README = Path(os.environ.get("PROXY_README_FILE", ROOT / "README.md"))
PROJECT_NAME = "Codex DMX Proxy"
PROJECT_PATH = "codex-dmx-proxy"


def fail(message: str) -> None:
    raise SystemExit(f"Markdown presentation contract: {message}")


def main() -> None:
    text = ROOT_README.read_text(encoding="utf-8")
    table = (
        "| Project identity | Value |\n"
        "| --- | --- |\n"
        f"| **GitLab Project Name** | `{PROJECT_NAME}` |\n"
        f"| **GitLab repository path** | `{PROJECT_PATH}` |\n"
        "| **GitHub repository** | `HengYangDS/codex-dmx-proxy` |\n"
        "| **License** | [MIT](LICENSE) |"
    )
    if table not in text:
        fail("README dual-forge project identity must use one semantic table")
    if re.search(
        r"^\*\*GitLab Project Name:\*\*[^\n]*(?<!  )\n\*\*GitLab repository path:\*\*",
        text,
        flags=re.MULTILINE,
    ):
        fail("adjacent project metadata rows would collapse without an explicit structure")
    print("Markdown presentation contract: OK")


if __name__ == "__main__":
    main()
