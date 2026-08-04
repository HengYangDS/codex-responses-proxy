"""Single owner for portable paths and validated process-local settings."""

from __future__ import annotations

import math
import ntpath
import os
import posixpath
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

HOME_ENV = "CODEX_RESPONSES_PROXY_HOME"
STATE_HOME_ENV = "CODEX_RESPONSES_PROXY_STATE_HOME"
PROXY_PORT_ENV = "CODEX_RESPONSES_PROXY_PROXY_PORT"
PROXY_PYTHON_ENV = "CODEX_RESPONSES_PROXY_PROXY_PYTHON"
PROXY_SCRIPT_ENV = "CODEX_RESPONSES_PROXY_PROXY_SCRIPT"
PROXY_LOG_ENV = "CODEX_RESPONSES_PROXY_PROXY_LOG"
WATCHDOG_LOG_ENV = "CODEX_RESPONSES_PROXY_WATCHDOG_LOG"
PROXY_LOG_MAX_BYTES_ENV = "CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES"
PROXY_LOG_BACKUP_COUNT_ENV = "CODEX_RESPONSES_PROXY_PROXY_LOG_BACKUP_COUNT"
WATCHDOG_LOG_MAX_BYTES_ENV = "CODEX_RESPONSES_PROXY_WATCHDOG_LOG_MAX_BYTES"
WATCHDOG_LOG_BACKUP_COUNT_ENV = "CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT"
RESPONSES_MAX_CONCURRENCY_ENV = "CODEX_RESPONSES_PROXY_RESPONSES_MAX_CONCURRENCY"
RESPONSES_MAX_PER_ROUTE_ENV = "CODEX_RESPONSES_PROXY_RESPONSES_MAX_PER_ROUTE"
RESPONSES_QUEUE_TIMEOUT_ENV = "CODEX_RESPONSES_PROXY_RESPONSES_QUEUE_TIMEOUT"
UPSTREAM_TIMEOUT_ENV = "CODEX_RESPONSES_PROXY_UPSTREAM_TIMEOUT"
UPSTREAM_READ_TIMEOUT_ENV = "CODEX_RESPONSES_PROXY_UPSTREAM_READ_TIMEOUT"
WATCHDOG_INTERVAL_ENV = "CODEX_RESPONSES_PROXY_WATCHDOG_INTERVAL"
WATCHDOG_MAX_BACKOFF_ENV = "CODEX_RESPONSES_PROXY_WATCHDOG_MAX_BACKOFF"

DEFAULT_PORT = 8792
DEFAULT_PROXY_LOG_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_PROXY_LOG_BACKUP_COUNT = 3
DEFAULT_WATCHDOG_LOG_MAX_BYTES = 512 * 1024
DEFAULT_WATCHDOG_LOG_BACKUP_COUNT = 2
DEFAULT_RESPONSES_MAX_CONCURRENCY = 8
DEFAULT_RESPONSES_MAX_PER_ROUTE = DEFAULT_RESPONSES_MAX_CONCURRENCY // 2
DEFAULT_UPSTREAM_TIMEOUT = 900.0
DEFAULT_UPSTREAM_READ_TIMEOUT = 240.0
DEFAULT_RESPONSES_QUEUE_TIMEOUT = DEFAULT_UPSTREAM_TIMEOUT
DEFAULT_WATCHDOG_INTERVAL = 15.0
DEFAULT_WATCHDOG_MAX_BACKOFF = 120.0


class ConfigurationError(ValueError):
    """A supplied runtime setting is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class LogRetention:
    """One bounded rotating-log policy."""

    path: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated process-local configuration shared by every runtime owner."""

    host: str
    port: int
    proxy_log: LogRetention
    watchdog_log: LogRetention
    responses_max_concurrency: int
    responses_max_per_route: int
    responses_queue_timeout: float
    upstream_timeout: float
    upstream_read_timeout: float
    watchdog_interval: float
    watchdog_max_backoff: float

    @property
    def listener(self) -> tuple[str, int]:
        """Return the immutable local listener address."""

        return self.host, self.port


def home_dir() -> str:
    """Return the active user's expanded home directory."""

    return os.path.expanduser("~")


def path_join(root: str, *parts: str) -> str:
    """Join an owned path without reinterpreting its existing platform syntax."""

    if PureWindowsPath(root).drive or "\\" in root:
        return ntpath.join(root, *parts)
    return posixpath.join(root, *parts)


def _absolute_override(source: Mapping[str, str], name: str) -> str | None:
    raw = source.get(name)
    if not raw:
        return None
    if raw == "~" or raw.startswith(("~/", "~\\")):
        home = source.get("HOME") or source.get("USERPROFILE") or home_dir()
        raw = path_join(home, raw[2:].replace("\\", "/")) if len(raw) > 1 else home
    if PurePosixPath(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
        return raw
    return os.path.abspath(raw)


def data_dir(environment: Mapping[str, str] | None = None) -> str:
    """Return the portable product data root, allowing an explicit override."""

    source = os.environ if environment is None else environment
    if override := _absolute_override(source, HOME_ENV):
        return override
    home = home_dir()
    if os.name == "nt":
        base = source.get("LOCALAPPDATA", path_join(home, "AppData", "Local"))
        return path_join(base, "codex-responses-proxy")
    if sys.platform == "darwin":
        return path_join(home, "Library", "Application Support", "codex-responses-proxy")
    base = source.get("XDG_DATA_HOME", path_join(home, ".local", "share"))
    return path_join(base, "codex-responses-proxy")


def state_dir(environment: Mapping[str, str] | None = None) -> str:
    """Return the portable product state root, allowing an explicit override."""

    source = os.environ if environment is None else environment
    if override := _absolute_override(source, STATE_HOME_ENV):
        return override
    home = home_dir()
    if os.name == "nt":
        base = source.get("LOCALAPPDATA", path_join(home, "AppData", "Local"))
        return path_join(base, "codex-responses-proxy", "state")
    if sys.platform == "darwin":
        return path_join(home, "Library", "Logs", "codex-responses-proxy")
    base = source.get("XDG_STATE_HOME", path_join(home, ".local", "state"))
    return path_join(base, "codex-responses-proxy")


def listener_host() -> str:
    """Return the product-invariant loopback listener host."""

    return "127.0.0.1"


def _integer(source: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = source.get(name, str(default))
    if isinstance(raw, bool):
        raise ConfigurationError(f"{name} must be an integer in {minimum}..{maximum}")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{name} must be an integer in {minimum}..{maximum}") from None
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _number(
    source: Mapping[str, str], name: str, default: float, minimum: float, maximum: float
) -> float:
    raw = source.get(name, str(default))
    if isinstance(raw, bool):
        raise ConfigurationError(f"{name} must be a finite number in {minimum:g}..{maximum:g}")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(
            f"{name} must be a finite number in {minimum:g}..{maximum:g}"
        ) from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be a finite number in {minimum:g}..{maximum:g}")
    return value


def listener_port(environment: Mapping[str, str] | None = None) -> int:
    """Return the configured TCP port after strict range validation."""

    source = os.environ if environment is None else environment
    return _integer(source, PROXY_PORT_ENV, DEFAULT_PORT, 1, 65535)


def proxy_log_path(environment: Mapping[str, str] | None = None) -> str:
    """Return the proxy log path owned by the portable state root."""

    source = os.environ if environment is None else environment
    return source.get(PROXY_LOG_ENV, path_join(state_dir(source), "proxy.log"))


def watchdog_log_path(environment: Mapping[str, str] | None = None) -> str:
    """Return the watchdog log path owned by the portable state root."""

    source = os.environ if environment is None else environment
    return source.get(WATCHDOG_LOG_ENV, path_join(state_dir(source), "watchdog.log"))


def load(environment: Mapping[str, str] | None = None) -> Settings:
    """Load every process-local setting once and reject unsafe values."""

    source = os.environ if environment is None else environment
    return Settings(
        host=listener_host(),
        port=listener_port(source),
        proxy_log=LogRetention(
            path=proxy_log_path(source),
            max_bytes=_integer(
                source,
                PROXY_LOG_MAX_BYTES_ENV,
                DEFAULT_PROXY_LOG_MAX_BYTES,
                4 * 1024,
                64 * 1024 * 1024,
            ),
            backup_count=_integer(
                source, PROXY_LOG_BACKUP_COUNT_ENV, DEFAULT_PROXY_LOG_BACKUP_COUNT, 0, 10
            ),
        ),
        watchdog_log=LogRetention(
            path=watchdog_log_path(source),
            max_bytes=_integer(
                source,
                WATCHDOG_LOG_MAX_BYTES_ENV,
                DEFAULT_WATCHDOG_LOG_MAX_BYTES,
                4 * 1024,
                64 * 1024 * 1024,
            ),
            backup_count=_integer(
                source,
                WATCHDOG_LOG_BACKUP_COUNT_ENV,
                DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
                0,
                10,
            ),
        ),
        responses_max_concurrency=_integer(
            source, RESPONSES_MAX_CONCURRENCY_ENV, DEFAULT_RESPONSES_MAX_CONCURRENCY, 1, 4096
        ),
        responses_max_per_route=_integer(
            source, RESPONSES_MAX_PER_ROUTE_ENV, DEFAULT_RESPONSES_MAX_PER_ROUTE, 1, 4096
        ),
        responses_queue_timeout=_number(
            source, RESPONSES_QUEUE_TIMEOUT_ENV, DEFAULT_RESPONSES_QUEUE_TIMEOUT, 0.001, 3600
        ),
        upstream_timeout=_number(
            source, UPSTREAM_TIMEOUT_ENV, DEFAULT_UPSTREAM_TIMEOUT, 0.001, 3600
        ),
        upstream_read_timeout=_number(
            source, UPSTREAM_READ_TIMEOUT_ENV, DEFAULT_UPSTREAM_READ_TIMEOUT, 0.001, 3600
        ),
        watchdog_interval=_number(
            source, WATCHDOG_INTERVAL_ENV, DEFAULT_WATCHDOG_INTERVAL, 0.1, 3600
        ),
        watchdog_max_backoff=_number(
            source, WATCHDOG_MAX_BACKOFF_ENV, DEFAULT_WATCHDOG_MAX_BACKOFF, 0.1, 86400
        ),
    )
