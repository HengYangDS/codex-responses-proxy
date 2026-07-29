#!/usr/bin/env python3
"""Shared construction helpers for repository behavior tests."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_adapters import common, payload  # noqa: E402


def install_context(root: Path) -> common.InstallContext:
    """Build an isolated install context rooted below ``root``."""

    install_dir = root / ".codex" / "dmx-proxy"
    return common.InstallContext(
        home=str(root),
        install_dir=str(install_dir),
        proxy_script=str(install_dir / "proxy" / "dmx_responses_proxy.py"),
        watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
        python=sys.executable,
        codex_config=str(root / ".codex" / "config.toml"),
        log_dir=str(root / ".codex" / "log"),
        port=8791,
        upstream="https://www.dmxapi.cn",
    )


def platform_context(
    port: int = 8791, upstream: str = "https://www.dmxapi.cn"
) -> common.InstallContext:
    """Build the deterministic cross-platform service-definition fixture."""

    return common.InstallContext(
        home="/home/tester",
        install_dir="/home/tester/.codex/dmx-proxy",
        proxy_script="/home/tester/.codex/dmx-proxy/proxy/dmx_responses_proxy.py",
        watchdog_script="/home/tester/.codex/dmx-proxy/watchdog/watchdog.py",
        python="/usr/bin/python3.12",
        codex_config="/home/tester/.codex/config.toml",
        log_dir="/home/tester/.codex/log",
        port=port,
        upstream=upstream,
    )


def control_plane_source(root: Path) -> Path:
    """Copy the declared runtime payload into a controller-source fixture."""

    source = root / "source"
    for relative in payload.RUNTIME_PAYLOAD_FILES:
        origin = ROOT / relative
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    return source


def assert_private_log_mode(testcase, mode: int) -> None:
    """Assert the strongest portable privacy bits exposed by the host."""

    if os.name == "nt":
        testcase.assertEqual(mode & 0o600, 0o600)
    else:
        testcase.assertEqual(mode, 0o600)
