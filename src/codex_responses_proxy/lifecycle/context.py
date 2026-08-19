"""One portable projection of an installed native product runtime."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import command
from codex_responses_proxy.runtime import config
from codex_responses_proxy.service import inventory


SERVICE_ID = "codex-responses-proxy.watchdog"
DEFAULT_PORT = config.DEFAULT_PORT


def service_id(install_dir: str) -> str:
    """Return one stable service identity bound to the installed payload root.

    The default user installation keeps the public service name.  Any explicit
    alternate root receives a deterministic suffix so isolated validation and
    parallel installations cannot unload or replace the user's live service.
    """

    installed = os.path.normcase(os.path.abspath(install_dir))
    canonical = os.path.normcase(os.path.abspath(config.default_data_dir()))
    if installed == canonical:
        return SERVICE_ID
    suffix = hashlib.sha256(installed.encode("utf-8")).hexdigest()[:12]
    return f"{SERVICE_ID}.{suffix}"


@dataclass(slots=True)
class RuntimeContext:
    """Absolute paths and validated settings for one installed projection."""

    home: str
    install_dir: str
    executable: str
    command: str
    log_dir: str
    port: int = config.DEFAULT_PORT
    proxy_log_max_bytes: int = config.DEFAULT_PROXY_LOG_MAX_BYTES
    proxy_log_backup_count: int = config.DEFAULT_PROXY_LOG_BACKUP_COUNT
    watchdog_log_max_bytes: int = config.DEFAULT_WATCHDOG_LOG_MAX_BYTES
    watchdog_log_backup_count: int = config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT
    upstream_timeout: float = config.DEFAULT_UPSTREAM_TIMEOUT
    upstream_read_timeout: float = config.DEFAULT_UPSTREAM_READ_TIMEOUT
    watchdog_interval: float = config.DEFAULT_WATCHDOG_INTERVAL
    watchdog_max_backoff: float = config.DEFAULT_WATCHDOG_MAX_BACKOFF
    response_failed_compaction_budget: int = config.DEFAULT_RESPONSE_FAILED_COMPACTION_BUDGET
    response_failed_max_stages: int = config.DEFAULT_RESPONSE_FAILED_MAX_STAGES

    @property
    def service_id(self) -> str:
        """Return the supervision identity for this installed root."""

        return service_id(self.install_dir)

    def service_environment(self) -> dict[str, str]:
        """Project the exact installer-selected settings into native supervision."""

        return {
            config.PROXY_PORT_ENV: str(self.port),
            config.PROXY_LOG_ENV: config.path_join(self.log_dir, "proxy.log"),
            config.WATCHDOG_LOG_ENV: config.path_join(self.log_dir, "watchdog.log"),
            config.PROXY_LOG_MAX_BYTES_ENV: str(self.proxy_log_max_bytes),
            config.PROXY_LOG_BACKUP_COUNT_ENV: str(self.proxy_log_backup_count),
            config.WATCHDOG_LOG_MAX_BYTES_ENV: str(self.watchdog_log_max_bytes),
            config.WATCHDOG_LOG_BACKUP_COUNT_ENV: str(self.watchdog_log_backup_count),
            config.UPSTREAM_TIMEOUT_ENV: str(self.upstream_timeout),
            config.UPSTREAM_READ_TIMEOUT_ENV: str(self.upstream_read_timeout),
            config.WATCHDOG_INTERVAL_ENV: str(self.watchdog_interval),
            config.WATCHDOG_MAX_BACKOFF_ENV: str(self.watchdog_max_backoff),
            config.RESPONSE_FAILED_COMPACTION_BUDGET_ENV: str(
                self.response_failed_compaction_budget
            ),
            config.RESPONSE_FAILED_MAX_STAGES_ENV: str(self.response_failed_max_stages),
        }


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


def create(
    *,
    executable: str | None = None,
    port: int = config.DEFAULT_PORT,
    proxy_log_max_bytes: int = config.DEFAULT_PROXY_LOG_MAX_BYTES,
    proxy_log_backup_count: int = config.DEFAULT_PROXY_LOG_BACKUP_COUNT,
    watchdog_log_max_bytes: int = config.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
    watchdog_log_backup_count: int = config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
) -> RuntimeContext:
    """Validate command inputs and project all product-owned paths once."""

    install_dir = config.data_dir()
    home = config.home_dir()
    return RuntimeContext(
        home=home,
        install_dir=install_dir,
        executable=executable
        or inventory.installed_executable(install_dir, windows=config.os.name == "nt"),
        command=str(command.path(home, config.os.environ, windows=config.os.name == "nt")),
        log_dir=config.state_dir(),
        port=validate_port(port),
        proxy_log_max_bytes=validate_log_retention(
            proxy_log_max_bytes,
            name="proxy log max bytes",
            minimum=4 * 1024,
            maximum=64 * 1024 * 1024,
        ),
        proxy_log_backup_count=validate_log_retention(
            proxy_log_backup_count,
            name="proxy log backup count",
            minimum=0,
            maximum=10,
        ),
        watchdog_log_max_bytes=validate_log_retention(
            watchdog_log_max_bytes,
            name="watchdog log max bytes",
            minimum=4 * 1024,
            maximum=64 * 1024 * 1024,
        ),
        watchdog_log_backup_count=validate_log_retention(
            watchdog_log_backup_count,
            name="watchdog log backup count",
            minimum=0,
            maximum=10,
        ),
    )
