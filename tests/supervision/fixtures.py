#!/usr/bin/env python3
"""Shared supervision test construction helpers."""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from tests.deployment.fixtures import platform_context


def completed(cmd=(), returncode=0, stdout="", stderr=""):
    """Build a deterministic completed-process result."""

    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


@contextmanager
def temporary_context(attribute):
    """Yield a platform context with one path rooted in a temporary directory."""

    with tempfile.TemporaryDirectory() as directory:
        context = platform_context()
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


def assert_fragments(testcase, text, include=(), exclude=()):
    """Assert required and forbidden fragments with useful subtest labels."""

    for fragment in include:
        with testcase.subTest(fragment=fragment):
            testcase.assertIn(fragment, text)
    for fragment in exclude:
        with testcase.subTest(fragment=fragment):
            testcase.assertNotIn(fragment, text)


def assert_executable_mode(testcase, mode):
    """Assert POSIX execution or the strongest Windows mode projection."""

    if os.name == "nt":
        testcase.assertEqual(mode & 0o600, 0o600)
    else:
        testcase.assertEqual(mode, 0o755)
