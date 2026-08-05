"""Human-readable projections of the public command result model."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Any

_LABEL_WIDTH = 12


def _width(value: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1 for character in value
    )


def _row(label: str, value: object) -> str:
    padding = max(1, _LABEL_WIDTH - _width(label))
    return f"  {label}{' ' * padding}{value}"


def _page(
    title: str, rows: Iterable[tuple[str, object]], *, next_command: str | None = None
) -> str:
    lines = [f"Codex Responses Proxy  {title}", "─" * 40, ""]
    lines.extend(_row(label, value) for label, value in rows)
    if next_command:
        lines.extend(("", "Next", f"  {next_command}"))
    return "\n".join(lines)


def render(command: str, result: Any) -> str:
    """Render one successful public command without exposing serialized internals."""

    if command == "version" or isinstance(result, str):
        return str(result)
    if not isinstance(result, dict):
        return ""
    if command == "status":
        integrity = result.get("payload_integrity")
        payload_ok = isinstance(integrity, dict) and integrity.get("ok") is True
        listeners = result.get("listener_pids")
        listener = "Unavailable"
        if isinstance(listeners, list) and len(listeners) == 1:
            listener = f"PID {listeners[0]}"
        return _page(
            "Status",
            (
                ("Release", result.get("release") or "Not installed"),
                ("Payload", "Verified" if payload_ok else "Action required"),
                ("Service", str(result.get("service") or "Unknown").capitalize()),
                ("Listener", listener),
            ),
            next_command="codex-responses-proxy doctor"
            if not payload_ok or listener == "Unavailable"
            else None,
        )
    if command == "doctor":
        checks = result.get("checks") if isinstance(result.get("checks"), dict) else {}
        rows = tuple(
            (
                str(name).capitalize(),
                "Passed" if check.get("status") == "passed" else "Action required",
            )
            for name, check in checks.items()
            if isinstance(check, dict)
        )
        next_command = next(
            (
                str(check["next"])
                .removeprefix("run `")
                .removesuffix("`, then inspect the service log")
                for check in checks.values()
                if isinstance(check, dict) and check.get("next")
            ),
            None,
        )
        return _page("Doctor", rows, next_command=next_command)
    if command == "install":
        runtime = result.get("runtime") if isinstance(result.get("runtime"), dict) else {}
        release = result.get("release") or runtime.get("release") or "Verified release"
        return _page(
            "Installed", (("Release", release),), next_command="codex-responses-proxy status"
        )
    if command == "reload":
        return _page(
            "Reloaded",
            (
                ("Previous PID", result.get("old_pid", "Unknown")),
                ("Current PID", result.get("new_pid", "Unknown")),
            ),
            next_command="codex-responses-proxy status",
        )
    if command == "uninstall":
        return _page(
            "Purged" if result.get("purged") else "Uninstalled",
            (
                ("Stopped", result.get("stopped", 0)),
                ("Payload", "Removed" if result.get("purged") else "Preserved"),
            ),
        )
    return ""


def error(message: str, *, next_command: str) -> str:
    """Render one bounded problem with a single safe next action."""

    return _page("Action required", (("Problem", message),), next_command=next_command)
