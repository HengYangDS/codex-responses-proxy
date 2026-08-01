#!/usr/bin/env python3
"""Shared construction helpers for repository behavior tests."""

from __future__ import annotations

import os
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.runtime import context as runtime_context  # noqa: E402
from codex_responses_proxy.payload import inventory
from codex_responses_proxy.payload import projection  # noqa: E402


def install_context(root: Path) -> runtime_context.RuntimeContext:
    """Build an isolated install context rooted below ``root``."""

    install_dir = root / "data" / "codex-responses-proxy"
    return runtime_context.RuntimeContext(
        home=str(root),
        install_dir=str(install_dir),
        proxy_script=str(install_dir / "codex_responses_proxy" / "listener" / "entrypoint.py"),
        watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
        python=sys.executable,
        log_dir=str(root / "state" / "codex-responses-proxy"),
        port=8791,
    )


def platform_context(port: int = 8791) -> runtime_context.RuntimeContext:
    """Build the deterministic cross-platform service-definition fixture."""

    return runtime_context.RuntimeContext(
        home="/home/tester",
        install_dir="/home/tester/.local/share/codex-responses-proxy",
        proxy_script="/home/tester/.local/share/codex-responses-proxy/codex_responses_proxy/listener/entrypoint.py",
        watchdog_script="/home/tester/.local/share/codex-responses-proxy/watchdog/watchdog.py",
        python="/usr/bin/python3.12",
        log_dir="/home/tester/.local/state/codex-responses-proxy",
        port=port,
    )


def assert_private_log_mode(testcase, mode: int) -> None:
    """Assert the strongest portable privacy bits exposed by the host."""

    if os.name == "nt":
        testcase.assertEqual(mode & 0o600, 0o600)
    else:
        testcase.assertEqual(mode, 0o600)


def write_retired_projection(
    ctx: runtime_context.RuntimeContext,
    *,
    version: str = "1.0.27",
    schema: int = 2,
    overrides: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    """Write one exact historical manifest inventory for lifecycle tests."""

    files = {
        relative: (f"{version}\n".encode() if relative == "VERSION" else f"{relative}\n".encode())
        for relative in projection._RETIRED_RUNTIME_FILES[schema]
    }
    files.update(overrides or {})
    if set(files) != set(projection._RETIRED_RUNTIME_FILES[schema]):
        raise AssertionError("retired fixture must match one exact historical inventory")
    install = Path(ctx.install_dir)
    for relative, content in files.items():
        target = install / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {
        "schema_version": schema,
        "release": version,
        "files": {
            relative: hashlib.sha256(content).hexdigest() for relative, content in files.items()
        },
    }
    (install / inventory.MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return files
