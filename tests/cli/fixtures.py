"""Capture one public CLI invocation without changing process arguments."""

from __future__ import annotations

import contextlib
import io

from codex_responses_proxy.cli import application


def invoke(*arguments: str) -> tuple[int, str, str]:
    """Return the exit code and captured public output streams."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = application.main(list(arguments))
    return code, stdout.getvalue(), stderr.getvalue()
