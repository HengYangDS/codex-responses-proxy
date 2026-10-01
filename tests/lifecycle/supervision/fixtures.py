"""Shared supervision test construction helpers."""

from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import platform_context


def completed(cmd=(), returncode=0, stdout="", stderr=""):
    """Build a deterministic completed-process result."""
    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


@contextmanager
def temporary_context(attribute, *, windows=False):
    """Yield a service context whose host-owned paths share one temporary root."""
    with tempfile.TemporaryDirectory() as directory:
        context = platform_context(windows=windows)
        context.user_home = directory
        context.install_dir = str(Path(directory, "payload"))
        context.executable = str(
            Path(context.install_dir, "bin", Path(inventory.executable_name(windows=windows)).name)
        )
        context.command = str(Path(directory, "command"))
        context.log_dir = str(Path(directory, "logs"))
        setattr(context, attribute, directory)
        if attribute == "install_dir":
            context.executable = str(
                Path(directory, "bin", Path(inventory.executable_name(windows=windows)).name)
            )
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
