"""Single public command grammar for Codex Responses Proxy."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import control, install, uninstall
from codex_responses_proxy.service import runtime as service_runtime

PUBLIC_COMMANDS = frozenset({"install", "status", "doctor", "reload", "uninstall", "version"})
_FAILURE_STATUS = "failed"
_RECOVERY_NEXT = "run `codex-responses-proxy reload`, then inspect the service log"


class _Parser(argparse.ArgumentParser):
    """Return parse failures to the application boundary instead of exiting."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message, sys.stderr)
        if not status:
            raise _HelpRequested
        raise ValueError(message or "invalid arguments")


class _HelpRequested(Exception):
    """Internal control flow for a successfully rendered help page."""


class _HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None) -> None:
        parser.print_help()
        raise _HelpRequested


def _parser() -> _Parser:
    parser = _Parser(prog="codex-responses-proxy", description=__doc__, add_help=False)
    parser.add_argument("-h", "--help", action=_HelpAction, nargs=0, help="show this help message")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command, help_text in (
        ("install", "install or upgrade the native user service"),
        ("status", "show installed state and listener health"),
        ("doctor", "diagnose the installed product without mutation"),
        ("reload", "transactionally reload the installed service"),
        ("uninstall", "remove the native service and owned state"),
        ("version", "print the product version"),
    ):
        subparser = commands.add_parser(command, help=help_text, add_help=False)
        subparser.add_argument(
            "-h", "--help", action=_HelpAction, nargs=0, help="show this help message"
        )
        if command in {"status", "doctor", "reload"}:
            subparser.add_argument("--json", action="store_true", dest="as_json")
        if command == "install":
            subparser.add_argument("--asset", type=Path, required=True)
            subparser.add_argument("--trust-anchor", type=Path, required=True)
            subparser.add_argument("--port", type=int, default=runtime_context.DEFAULT_PORT)
        if command in {"status", "doctor", "reload", "uninstall"}:
            subparser.add_argument("--port", type=int, default=runtime_context.DEFAULT_PORT)
        if command == "reload":
            subparser.add_argument("--timeout-seconds", type=float, default=30.0)
        if command == "uninstall":
            subparser.add_argument("--purge", action="store_true")
    return parser


def _release_version() -> str:
    if bundle_root := getattr(sys, "_MEIPASS", None):
        return (Path(bundle_root) / "VERSION").read_text(encoding="utf-8").strip()
    if source_version := _source_version():
        return source_version
    return importlib.metadata.version("codex-responses-proxy")


def _source_version() -> str | None:
    """Read repository metadata only when this module is actually under its ``src`` root."""

    source_root = Path(__file__).resolve().parents[2]
    repository = source_root.parent
    if source_root.name != "src" or not (repository / "pyproject.toml").is_file():
        return None
    return (repository / "VERSION").read_text(encoding="utf-8").strip()


def dispatch(command: str, arguments: argparse.Namespace) -> Any:
    """Execute one parsed command through its semantic owner."""

    if command == "version":
        return _release_version()
    if command == "install":
        return install.install_asset(
            arguments.asset,
            trust_anchor=arguments.trust_anchor,
            port=arguments.port,
        )
    if command == "uninstall":
        return uninstall.uninstall_product(port=arguments.port, purge=arguments.purge)
    context = control._context(arguments.port)
    if command == "status":
        return control.status(context)
    if command == "doctor":
        return _doctor(control.status(context))
    if command == "reload":
        return control.reload(context, timeout_seconds=arguments.timeout_seconds)
    raise ValueError(f"{command} is not implemented")


def _doctor(evidence: dict[str, Any]) -> dict[str, Any]:
    """Classify installed state without introducing another observation path."""

    integrity = evidence.get("payload_integrity")
    integrity_ok = isinstance(integrity, dict) and integrity.get("ok") is True
    service = evidence.get("service")
    runtime = evidence.get("runtime")
    listeners = evidence.get("listener_pids")
    listener_ok = (
        isinstance(runtime, dict)
        and isinstance(listeners, list)
        and len(listeners) == 1
        and type(runtime.get("pid")) is int
        and runtime["pid"] == listeners[0]
        and runtime.get("accepting") is not False
    )
    checks = {
        "payload": {
            "status": "passed" if integrity_ok else _FAILURE_STATUS,
            "detail": integrity.get("detail", "unavailable")
            if isinstance(integrity, dict)
            else "unavailable",
            "next": None
            if integrity_ok
            else "reinstall the verified release before changing client configuration",
        },
        "service": {
            "status": "passed" if service == "running" else _FAILURE_STATUS,
            "detail": str(service or "unknown"),
            "next": None if service == "running" else _RECOVERY_NEXT,
        },
        "listener": {
            "status": "passed" if listener_ok else _FAILURE_STATUS,
            "detail": "accepting" if listener_ok else "unavailable or identity mismatch",
            "next": None if listener_ok else _RECOVERY_NEXT,
        },
    }
    return {"ok": all(check["status"] == "passed" for check in checks.values()), "checks": checks}


def _render(command: str, result: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True))
    elif isinstance(result, str):
        print(result)
    elif result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))


def _result_code(command: str, result: Any) -> int:
    """Return a stable nonzero diagnostic status without treating it as an exception."""

    return (
        1 if command == "doctor" and isinstance(result, dict) and result.get("ok") is False else 0
    )


def _error(message: str, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"error": {"message": message}}, sort_keys=True), file=sys.stderr)
    else:
        print(f"error: {message}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one public command without leaking expected exceptions or warnings."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0].startswith("--internal-"):
        return _run_internal(arguments)
    if arguments and not arguments[0].startswith("-") and arguments[0] not in PUBLIC_COMMANDS:
        _error(f"unknown command: {arguments[0]}", as_json="--json" in arguments)
        return 2
    parser = _parser()
    try:
        parsed = parser.parse_args(arguments)
    except _HelpRequested:
        return 0
    except ValueError as error:
        _error(str(error), as_json="--json" in arguments)
        return 2
    if parsed.command is None:
        parser.print_help()
        return 0 if not arguments or "--help" in arguments else 2
    try:
        result = dispatch(parsed.command, parsed)
    except (OSError, RuntimeError, ValueError) as error:
        _error(str(error), as_json=bool(getattr(parsed, "as_json", False)))
        return 2
    _render(parsed.command, result, as_json=bool(getattr(parsed, "as_json", False)))
    return _result_code(parsed.command, result)


def _run_internal(arguments: list[str]) -> int:
    """Dispatch one exact private service role without adding it to public help."""

    if len(arguments) != 1:
        _error("internal service mode accepts no additional arguments", as_json=False)
        return 2
    mode = arguments[0]
    if mode == service_runtime.LISTENER_MODE:
        from codex_responses_proxy.service import entrypoint

        return entrypoint.run()
    if mode == service_runtime.HANDOFF_CHILD_MODE:
        from codex_responses_proxy.service import entrypoint

        return entrypoint.run(handoff_child=True)
    if mode == service_runtime.WATCHDOG_MODE:
        from codex_responses_proxy.lifecycle.supervision import watchdog

        watchdog.run()
        return 0
    _error("unknown internal service mode", as_json=False)
    return 2
