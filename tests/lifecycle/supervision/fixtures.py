"""Shared supervision test construction helpers."""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from tests.lifecycle.fixtures import platform_context


def completed(cmd=(), returncode=0, stdout="", stderr=""):
    """Build a deterministic completed-process result."""

    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


@contextmanager
def temporary_context(attribute, *, windows=False):
    """Yield a platform context with one path rooted in a temporary directory."""

    with tempfile.TemporaryDirectory() as directory:
        context = platform_context(windows=windows)
        setattr(context, attribute, directory)
        yield context


def set_file(path, text=None):
    """Create or remove a text fixture and return its path."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def assert_fragments(text, include=(), exclude=()):
    """Assert required and forbidden fragments."""

    for fragment in include:
        assert fragment in text
    for fragment in exclude:
        assert fragment not in text


def assert_executable_mode(testcase, mode):
    """Assert POSIX execution or the strongest Windows mode projection."""

    if os.name == "nt":
        assert mode & 384 == 384
    else:
        assert mode == 493
