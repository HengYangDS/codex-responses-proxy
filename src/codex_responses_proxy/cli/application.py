"""Single public command grammar for Codex Responses Proxy."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

from cyclopts import App, Parameter
from rich.console import Console

from codex_responses_proxy.cli import presentation
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import control, install, transaction, uninstall
from codex_responses_proxy.service import runtime as service_runtime

PUBLIC_COMMANDS = frozenset(
    {"install", "status", "doctor", "recover", "reload", "uninstall", "version"}
)
_FAILURE_STATUS = "failed"
_RECOVERY_NEXT = "run `codex-responses-proxy reload`, then inspect the service log"
_JSON = Annotated[bool, Parameter(name="--json", negative=False)]


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


def dispatch(command: str, **arguments: Any) -> Any:
    """Execute one parsed command through its semantic owner."""

    if command == "version":
        return _release_version()
    if command == "install":
        return install.install_asset(
            arguments["asset"],
            trust_anchor=arguments["trust_anchor"],
            port=arguments["port"],
        )
    if command == "uninstall":
        return uninstall.uninstall_product(port=arguments["port"], purge=arguments["purge"])
    context = control._context(arguments["port"])
    if command == "status":
        return control.status(context)
    if command == "doctor":
        return _doctor(control.status(context))
    if command == "recover":
        return transaction.rollback_recovery(context, runtime=control._runtime_metrics(context))
    if command == "reload":
        return control.reload(context, timeout_seconds=arguments["timeout_seconds"])
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
        return
    rendered = presentation.render(command, result)
    if rendered:
        print(rendered)


def _result_code(command: str, result: Any) -> int:
    """Return a stable nonzero diagnostic status without treating it as an exception."""

    return 1 if command == "doctor" and isinstance(result, dict) and not result.get("ok") else 0


def _error(message: str, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"error": {"message": message}}, sort_keys=True), file=sys.stderr)
    else:
        print(
            presentation.error(message, next_command="codex-responses-proxy doctor"),
            file=sys.stderr,
        )


def _execute(command: str, *, as_json: bool = False, **arguments: Any) -> int:
    try:
        result = dispatch(command, **arguments)
    except (OSError, RuntimeError, ValueError) as error:
        _error(str(error), as_json=as_json)
        return 2
    _render(command, result, as_json=as_json)
    return _result_code(command, result)


def _app() -> App:
    app = App(
        name="codex-responses-proxy",
        help=__doc__,
        version_flags=[],
        print_error=False,
        exit_on_error=False,
        result_action="return_value",
        help_format="rich",
    )

    @app.command(name="install")
    def install_command(
        *,
        asset: Path,
        trust_anchor: Annotated[Path, Parameter(name="--trust-anchor")],
        port: int = runtime_context.DEFAULT_PORT,
    ) -> int:
        """Install or upgrade the native user service."""

        return _execute("install", asset=asset, trust_anchor=trust_anchor, port=port)

    @app.command(name="status")
    def status_command(
        *, json_output: _JSON = False, port: int = runtime_context.DEFAULT_PORT
    ) -> int:
        """Show installed state and listener health."""

        return _execute("status", as_json=json_output, port=port)

    @app.command(name="doctor")
    def doctor(*, json_output: _JSON = False, port: int = runtime_context.DEFAULT_PORT) -> int:
        """Diagnose the installed product without mutation."""

        return _execute("doctor", as_json=json_output, port=port)

    @app.command(name="recover")
    def recover(*, json_output: _JSON = False, port: int = runtime_context.DEFAULT_PORT) -> int:
        """Restore a retained failed installation transaction."""

        return _execute("recover", as_json=json_output, port=port)

    @app.command(name="reload")
    def reload_command(
        *,
        json_output: _JSON = False,
        port: int = runtime_context.DEFAULT_PORT,
        timeout_seconds: Annotated[float, Parameter(name="--timeout-seconds")] = 30.0,
    ) -> int:
        """Transactionally reload the installed service."""

        return _execute("reload", as_json=json_output, port=port, timeout_seconds=timeout_seconds)

    @app.command(name="uninstall")
    def uninstall_command(*, port: int = runtime_context.DEFAULT_PORT, purge: bool = False) -> int:
        """Remove the native service and optionally its owned state."""

        return _execute("uninstall", port=port, purge=purge)

    @app.command
    def version() -> int:
        """Print the product version."""

        return _execute("version")

    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Run one public command without leaking expected exceptions or warnings."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0].startswith("--internal-"):
        return _run_internal(arguments)
    if arguments and not arguments[0].startswith("-") and arguments[0] not in PUBLIC_COMMANDS:
        _error(f"unknown command: {arguments[0]}", as_json="--json" in arguments)
        return 2
    try:
        result = _app()(arguments, console=Console(), error_console=Console(stderr=True))
    except Exception as error:
        _error(str(error), as_json="--json" in arguments)
        return 2
    return result if isinstance(result, int) else 0


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
