"""Canonical, secret-free configuration for one installed native runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, Protocol

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.runtime import config
from codex_responses_proxy.service import digest, inventory

if TYPE_CHECKING:
    from codex_responses_proxy.lifecycle.context import RuntimeContext

FILENAME = inventory.RUNTIME_CONFIG_FILENAME
SCHEMA_VERSION = 1

_FIELDS = (
    "install_dir",
    "log_dir",
    "port",
    "proxy_log_max_bytes",
    "proxy_log_backup_count",
    "watchdog_log_max_bytes",
    "watchdog_log_backup_count",
    "upstream_timeout",
    "upstream_read_timeout",
    "watchdog_interval",
    "watchdog_max_backoff",
    "response_failed_compaction_budget",
    "response_failed_max_stages",
)


class NativeServiceContext(Protocol):
    """Minimum context consumed by every native service adapter."""

    @property
    def install_dir(self) -> str: ...

    @property
    def executable(self) -> str: ...

    @property
    def log_dir(self) -> str: ...

    @property
    def service_id(self) -> str: ...


def path(ctx: RuntimeContext) -> Path:
    """Return the product-owned configuration carrier for ``ctx``."""

    return Path(ctx.install_dir, FILENAME)


def write(ctx: RuntimeContext) -> Path:
    """Atomically persist the exact native runtime contract."""

    target = path(ctx)
    payload = _payload({name: getattr(ctx, name) for name in _FIELDS})
    owned_files.write_bytes(
        target,
        digest.canonical_json(payload),
        mode=0o600,
        root=Path(ctx.install_dir),
    )
    return target


def environment(target: Path) -> dict[str, str]:
    """Validate one carrier and project it into process-local settings."""

    return _project(_read(target))


def _project(value: dict[str, Any]) -> dict[str, str]:
    return {
        config.HOME_ENV: value["install_dir"],
        config.STATE_HOME_ENV: value["log_dir"],
        config.PROXY_PORT_ENV: str(value["port"]),
        config.PROXY_LOG_ENV: config.path_join(value["log_dir"], "proxy.log"),
        config.WATCHDOG_LOG_ENV: config.path_join(value["log_dir"], "watchdog.log"),
        config.PROXY_LOG_MAX_BYTES_ENV: str(value["proxy_log_max_bytes"]),
        config.PROXY_LOG_BACKUP_COUNT_ENV: str(value["proxy_log_backup_count"]),
        config.WATCHDOG_LOG_MAX_BYTES_ENV: str(value["watchdog_log_max_bytes"]),
        config.WATCHDOG_LOG_BACKUP_COUNT_ENV: str(value["watchdog_log_backup_count"]),
        config.UPSTREAM_TIMEOUT_ENV: str(value["upstream_timeout"]),
        config.UPSTREAM_READ_TIMEOUT_ENV: str(value["upstream_read_timeout"]),
        config.WATCHDOG_INTERVAL_ENV: str(value["watchdog_interval"]),
        config.WATCHDOG_MAX_BACKOFF_ENV: str(value["watchdog_max_backoff"]),
        config.RESPONSE_FAILED_COMPACTION_BUDGET_ENV: str(
            value["response_failed_compaction_budget"]
        ),
        config.RESPONSE_FAILED_MAX_STAGES_ENV: str(value["response_failed_max_stages"]),
    }


def from_executable(executable: str | os.PathLike[str]) -> Path:
    """Locate the carrier owned by the executable's installed payload root."""

    path = Path(executable).resolve(strict=True)
    if path.parent.name != "bin":
        raise errors.InstallError("native executable is outside the installed payload layout")
    return path.parent.parent / FILENAME


def activate(executable: str | os.PathLike[str]) -> Path:
    """Replace inherited product settings with the executable-owned carrier."""

    target = from_executable(executable)
    projected = environment(target)
    for name in config.RUNTIME_ENVIRONMENT:
        os.environ.pop(name, None)
    os.environ.update(projected)
    return target


def _payload(values: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, **values}


@dataclass(frozen=True, slots=True)
class ServiceContext:
    """Minimum native-service projection reconstructed inside the payload."""

    install_dir: str
    executable: str
    log_dir: str

    @property
    def service_id(self) -> str:
        from codex_responses_proxy.lifecycle.context import service_id

        return service_id(self.install_dir)


def service_context(executable: str) -> ServiceContext:
    """Reconstruct the exact native-service projection from its carrier."""

    target = from_executable(executable)
    value = _read(target)
    expected = inventory.installed_executable(
        value["install_dir"],
        windows=PureWindowsPath(executable).suffix.lower() == ".exe",
    )
    if _normalized(executable) != _normalized(expected):
        raise errors.InstallError("runtime configuration executable does not match its payload")
    return ServiceContext(
        install_dir=value["install_dir"],
        executable=executable,
        log_dir=value["log_dir"],
    )


def _read(target: Path) -> dict[str, Any]:
    value = owned_files.read_canonical_json(target, "native runtime configuration")
    if value.get("schema_version") != SCHEMA_VERSION or set(value) != {
        "schema_version",
        *_FIELDS,
    }:
        raise errors.InstallError("native runtime configuration schema is unsupported")
    for name in ("install_dir", "log_dir"):
        if not isinstance(value.get(name), str) or not _absolute(value[name]):
            raise errors.InstallError(f"native runtime configuration {name} is invalid")
    expected = Path(value["install_dir"], FILENAME)
    if _normalized(target) != _normalized(expected):
        raise errors.InstallError("native runtime configuration is outside its payload")
    try:
        config.load(_project(value))
    except config.ConfigurationError as exc:
        raise errors.InstallError(str(exc)) from exc
    return value


def _absolute(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _normalized(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(value))))
