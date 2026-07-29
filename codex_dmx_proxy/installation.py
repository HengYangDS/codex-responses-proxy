"""Validated installation context and workstation path conventions."""

from __future__ import annotations

import os
from dataclasses import dataclass

from codex_dmx_proxy import errors


LABEL = "com.user.codex-dmx-watchdog"
DEFAULT_PORT = 8791
DEFAULT_UPSTREAM = "https://www.dmxapi.cn"
DEFAULT_PROXY_LOG_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_PROXY_LOG_BACKUP_COUNT = 3
DEFAULT_WATCHDOG_LOG_MAX_BYTES = 512 * 1024
DEFAULT_WATCHDOG_LOG_BACKUP_COUNT = 2


@dataclass
class InstallContext:
    """Absolute paths and validated settings for one installed projection."""

    home: str
    install_dir: str
    proxy_script: str
    watchdog_script: str
    python: str
    codex_config: str
    log_dir: str
    port: int = DEFAULT_PORT
    upstream: str = DEFAULT_UPSTREAM
    proxy_log_max_bytes: int = DEFAULT_PROXY_LOG_MAX_BYTES
    proxy_log_backup_count: int = DEFAULT_PROXY_LOG_BACKUP_COUNT
    watchdog_log_max_bytes: int = DEFAULT_WATCHDOG_LOG_MAX_BYTES
    watchdog_log_backup_count: int = DEFAULT_WATCHDOG_LOG_BACKUP_COUNT


def home_dir() -> str:
    """Return the active user's expanded home directory."""

    return os.path.expanduser("~")


def codex_home() -> str:
    """Return ``CODEX_HOME`` or the active user's default Codex root."""

    return os.environ.get("CODEX_HOME", os.path.join(home_dir(), ".codex"))


def validate_port(port: int) -> int:
    """Accept only a real TCP port before service rendering."""

    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise errors.InstallError("port must be an integer in 1..65535")
    return port


def validate_log_retention(value: int, *, name: str, minimum: int, maximum: int) -> int:
    """Accept one bounded runtime-log retention setting."""

    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise errors.InstallError(f"{name} must be an integer in {minimum}..{maximum}")
    return value
