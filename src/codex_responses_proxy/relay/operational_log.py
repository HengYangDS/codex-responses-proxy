"""Bounded secret-safe operational logging for the proxy runtime."""

from __future__ import annotations

import os
import re
import stat
import sys
import threading
import time
import urllib.parse
from contextlib import suppress
from pathlib import Path

from codex_responses_proxy.runtime import config as runtime_config

SETTINGS = runtime_config.load()
LOG_PATH = SETTINGS.proxy_log.path
LOG_MAX_BYTES = SETTINGS.proxy_log.max_bytes
LOG_BACKUP_COUNT = SETTINGS.proxy_log.backup_count
LOG_LINE_MAX_BYTES = 1024
_LOG_LOCK = threading.Lock()
_LOG_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:authorization|api[_-]?key|bearer)\s*[:=]?\s*"
        r"(?:bearer\s+)?[^\s,;]+"
    ),
    re.compile(r"\bgAAAA[A-Za-z0-9_-]+"),
)


def safe_request_path(value: str) -> str:
    """Return a bounded request path without query values or caller text."""
    with suppress(TypeError, ValueError):
        path = urllib.parse.urlsplit(value).path
        if isinstance(path, str) and path.startswith("/"):
            return re.sub(r"[^A-Za-z0-9._~/-]", "_", path)[:192] or "/"
    return "/invalid-path"


def safe_exception_label(exc: BaseException | None) -> str:
    """Expose only the stable exception class, never an exception message."""
    return exc.__class__.__name__ if exc is not None else "UnknownError"


def _redact_log_message(message: str) -> str:
    value = str(message).replace("\r", " ").replace("\n", " ")
    for pattern in _LOG_SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    encoded = value.encode("utf-8", "replace")
    if len(encoded) > LOG_LINE_MAX_BYTES:
        value = encoded[:LOG_LINE_MAX_BYTES].decode("utf-8", "ignore") + " [truncated]"
    return value


def _rotate_log_if_needed(path: Path, incoming_bytes: int) -> int:
    """Enforce bounded local retention and return discarded legacy bytes."""
    try:
        metadata = path.lstat()
    except OSError:
        return 0
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("proxy log path is not a regular file")
    current_size = metadata.st_size
    if current_size + incoming_bytes <= LOG_MAX_BYTES:
        return 0

    discarded = 0
    match current_size > LOG_MAX_BYTES, LOG_BACKUP_COUNT > 0:
        case True, _:
            path.unlink(missing_ok=True)
            discarded += current_size
        case _, False:
            path.unlink(missing_ok=True)
        case _:
            path.with_name(f"{path.name}.{LOG_BACKUP_COUNT}").unlink(missing_ok=True)
            for index in range(LOG_BACKUP_COUNT - 1, 0, -1):
                source = path.with_name(f"{path.name}.{index}")
                exists = source.exists()
                size = source.stat().st_size if exists else 0
                match exists, size > LOG_MAX_BYTES:
                    case False, _:
                        pass
                    case True, True:
                        discarded += size
                        source.unlink(missing_ok=True)
                    case _:
                        source.replace(path.with_name(f"{path.name}.{index + 1}"))
            path.replace(path.with_name(f"{path.name}.1"))

    for index in range(1, LOG_BACKUP_COUNT + 1):
        segment = path.with_name(f"{path.name}.{index}")
        try:
            if segment.stat().st_size > LOG_MAX_BYTES:
                discarded += segment.stat().st_size
                segment.unlink()
        except OSError:
            continue
    return discarded


def log(message: str) -> None:
    """Write one bounded secret-safe operational line to disk and stderr."""
    safe_message = _redact_log_message(message)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {safe_message}\n"
    with suppress(OSError):
        path = Path(LOG_PATH)
        with _LOG_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            discarded = _rotate_log_if_needed(path, len(line.encode("utf-8", "replace")))
            if discarded:
                line = (
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"log_retention_discarded_oversized_bytes={discarded} {safe_message}\n"
                )
            with path.open("a", encoding="utf-8") as handle:
                with suppress(OSError):
                    os.chmod(path, 0o600)
                handle.write(line)
    with suppress(Exception):
        sys.stderr.write(line)
