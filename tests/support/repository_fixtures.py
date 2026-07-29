#!/usr/bin/env python3
"""Shared construction helpers for repository behavior tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy import installation  # noqa: E402


def install_context(root: Path) -> installation.InstallContext:
    """Build an isolated install context rooted below ``root``."""

    install_dir = root / ".codex" / "dmx-proxy"
    return installation.InstallContext(
        home=str(root),
        install_dir=str(install_dir),
        proxy_script=str(install_dir / "codex_dmx_proxy" / "listener" / "entrypoint.py"),
        watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
        python=sys.executable,
        codex_config=str(root / ".codex" / "config.toml"),
        log_dir=str(root / ".codex" / "log"),
        port=8791,
        upstream="https://www.dmxapi.cn",
    )


def platform_context(
    port: int = 8791, upstream: str = "https://www.dmxapi.cn"
) -> installation.InstallContext:
    """Build the deterministic cross-platform service-definition fixture."""

    return installation.InstallContext(
        home="/home/tester",
        install_dir="/home/tester/.codex/dmx-proxy",
        proxy_script="/home/tester/.codex/dmx-proxy/codex_dmx_proxy/listener/entrypoint.py",
        watchdog_script="/home/tester/.codex/dmx-proxy/watchdog/watchdog.py",
        python="/usr/bin/python3.12",
        codex_config="/home/tester/.codex/config.toml",
        log_dir="/home/tester/.codex/log",
        port=port,
        upstream=upstream,
    )


def assert_private_log_mode(testcase, mode: int) -> None:
    """Assert the strongest portable privacy bits exposed by the host."""

    if os.name == "nt":
        testcase.assertEqual(mode & 0o600, 0o600)
    else:
        testcase.assertEqual(mode, 0o600)
