"""Bounded secret-safe operational logging for the proxy runtime."""

from __future__ import annotations

import re
import sys
import urllib.parse
from contextlib import suppress
from pathlib import Path

from codex_responses_proxy.runtime import bounded_log
from codex_responses_proxy.runtime import config as runtime_config

SETTINGS = runtime_config.load()
LOG_PATH = SETTINGS.proxy_log.path
LOG_MAX_BYTES = SETTINGS.proxy_log.max_bytes
LOG_BACKUP_COUNT = SETTINGS.proxy_log.backup_count
LOG_LINE_MAX_BYTES = bounded_log.LINE_MAX_BYTES


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


def safe_exception_context(exc: BaseException | None) -> str:
    """Expose bounded transport metadata without caller-controlled messages."""
    fields = [f"exception={safe_exception_label(exc)}"]
    reason = getattr(exc, "reason", None)
    target = exc
    prefix = ""
    if isinstance(reason, BaseException):
        fields.append(f"reason_exception={safe_exception_label(reason)}")
        target = reason
        prefix = "reason_"
    for attribute in ("errno", "verify_code"):
        value = getattr(target, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            fields.append(f"{prefix}{attribute}={value}")
    return " ".join(fields)


def log(message: str) -> None:
    """Write one bounded secret-safe operational line to disk and stderr."""
    bounded_log.append(
        Path(LOG_PATH),
        message,
        max_bytes=LOG_MAX_BYTES,
        backup_count=LOG_BACKUP_COUNT,
        mirror=sys.stderr.write,
    )
