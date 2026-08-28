"""Single public command grammar for Codex Responses Proxy."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated
from typing import Literal
from typing import TypedDict
from typing import overload

from cyclopts import App
from cyclopts import Parameter
from cyclopts.exceptions import CycloptsError
from cyclopts.validators import Number
from rich.console import Console

from codex_responses_proxy import errors
from codex_responses_proxy import product_identity
from codex_responses_proxy.cli import presentation
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import install
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.lifecycle import uninstall
from codex_responses_proxy.service import runtime as service_runtime

PUBLIC_COMMANDS = frozenset(
    {"install", "status", "doctor", "recover", "reload", "rollback", "uninstall"}
)
_FAILURE_STATUS = "failed"
_RECOVERY_NEXT = product_identity.command("reload")
_JSON = Annotated[
    bool,
    Parameter(
        name="--json",
        negative=False,
        help="Emit stable JSON for automation.",
        show_default=False,
    ),
]
_PORT = Annotated[
    int,
    Parameter(
        help="Loopback listener port.",
        validator=Number(gte=1, lte=65535),
    ),
]
_TIMEOUT = Annotated[
    float,
    Parameter(
        name="--timeout-seconds",
        help="Native lifecycle deadline in seconds.",
        validator=Number(gt=0),
    ),
]
_PURGE = Annotated[
    bool,
    Parameter(
        name="--purge",
        negative=False,
        help="Remove verified product-owned data.",
        show_default=False,
    ),
]


class DoctorCheck(TypedDict):
    """One named diagnostic check."""

    status: str
    detail: object


class DoctorReport(TypedDict):
    """Stable doctor result consumed by humans and automation."""

    ok: bool
    state: object
    next: str | None
    checks: dict[str, DoctorCheck]


type CommandResult = Mapping[str, object] | None


def _release_version() -> str:
    if bundle_root := getattr(sys, "_MEIPASS", None):
        return (Path(bundle_root) / "VERSION").read_text(encoding="utf-8").strip()
    if source_version := _source_version():
        return source_version
    return importlib.metadata.version(product_identity.PACKAGE_NAME)


def _source_version() -> str | None:
    """Read repository metadata only when this module is actually under its ``src`` root."""
    source_root = Path(__file__).resolve().parents[2]
    repository = source_root.parent
    if source_root.name != "src" or not (repository / "pyproject.toml").is_file():
        return None
    return (repository / "VERSION").read_text(encoding="utf-8").strip()


def _path_argument(arguments: Mapping[str, object], name: str) -> Path:
    value = arguments.get(name)
    if not isinstance(value, Path):
        raise TypeError(f"{name} must be a path")
    return value


def _port_argument(arguments: Mapping[str, object]) -> int:
    value = arguments.get("port")
    if type(value) is not int:
        raise TypeError("port must be an integer")
    return value


def _timeout_argument(arguments: Mapping[str, object]) -> float:
    value = arguments.get("timeout_seconds", 30.0)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError("timeout_seconds must be numeric")
    return float(value)


def _purge_argument(arguments: Mapping[str, object]) -> bool:
    value = arguments.get("purge")
    if not isinstance(value, bool):
        raise TypeError("purge must be a boolean")
    return value


@overload
def dispatch(
    command: Literal["install", "status", "recover", "reload", "rollback", "uninstall"],
    **arguments: object,
) -> dict[str, object]: ...


@overload
def dispatch(command: Literal["doctor"], **arguments: object) -> DoctorReport: ...


@overload
def dispatch(command: str, **arguments: object) -> CommandResult: ...


def dispatch(command: str, **arguments: object) -> CommandResult:
    """Execute one parsed command through its semantic owner."""
    if command == "install":
        return install.install_asset(
            _path_argument(arguments, "asset"),
            trust_anchor=_path_argument(arguments, "trust_anchor"),
            port=_port_argument(arguments),
            timeout_seconds=_timeout_argument(arguments),
        )
    if command == "uninstall":
        return uninstall.uninstall_product(
            port=_port_argument(arguments), purge=_purge_argument(arguments)
        )
    context = runtime_context.create(port=_port_argument(arguments))
    if command == "status":
        return control.status(context)
    if command == "doctor":
        return _doctor(control.status(context))
    if command == "recover":
        return control.recover(context)
    if command == "reload":
        return control.reload(context, timeout_seconds=_timeout_argument(arguments))
    if command == "rollback":
        return control.rollback(context, timeout_seconds=_timeout_argument(arguments))
    raise ValueError(f"{command} is not implemented")


def _doctor(evidence: Mapping[str, object]) -> DoctorReport:
    """Classify installed state without introducing another observation path."""
    state = evidence.get("state")
    if state == "not_installed":
        return {
            "ok": False,
            "state": "not_installed",
            "next": product_identity.command("install", "--help"),
            "checks": {
                "installation": {
                    "status": _FAILURE_STATUS,
                    "detail": "not installed",
                }
            },
        }
    integrity = evidence.get("payload_integrity")
    integrity_ok = isinstance(integrity, dict) and integrity.get("ok") is True
    service = evidence.get("service")
    runtime = evidence.get("runtime")
    listener_ok = (
        isinstance(runtime, dict)
        and type(runtime.get("pid")) is int
        and runtime.get("accepting") is not False
    )
    command = evidence.get("command")
    command_ok = isinstance(command, dict) and command.get("state") == "owned"
    transaction_state = evidence.get("payload_transaction")
    transaction_ok = transaction_state is None
    rollback = evidence.get("rollback")
    rollback_ok = not isinstance(rollback, dict) or rollback.get("state") != "invalid"
    checks: dict[str, DoctorCheck] = {
        "payload": {
            "status": "passed" if integrity_ok else _FAILURE_STATUS,
            "detail": integrity.get("detail", "unavailable")
            if isinstance(integrity, dict)
            else "unavailable",
        },
        "service": {
            "status": "passed" if service == "running" else _FAILURE_STATUS,
            "detail": str(service or "unknown"),
        },
        "listener": {
            "status": "passed" if listener_ok else _FAILURE_STATUS,
            "detail": "accepting" if listener_ok else "unavailable or identity mismatch",
        },
        "command": {
            "status": "passed" if command_ok else _FAILURE_STATUS,
            "detail": str(command.get("path", "unavailable"))
            if isinstance(command, dict)
            else "unavailable",
        },
        "transaction": {
            "status": "passed" if transaction_ok else _FAILURE_STATUS,
            "detail": "none"
            if transaction_ok
            else str(transaction_state.get("state", "invalid"))
            if isinstance(transaction_state, dict)
            else "invalid",
        },
        "rollback": {
            "status": "passed" if rollback_ok else _FAILURE_STATUS,
            "detail": str(rollback.get("detail") or rollback.get("state", "unavailable"))
            if isinstance(rollback, dict)
            else "unavailable",
        },
    }
    next_command = (
        product_identity.command("status", "--json")
        if state == "invalid"
        else product_identity.command("recover")
        if state == "recovery_required"
        else product_identity.command("install", "--help")
        if not integrity_ok or not command_ok
        else _RECOVERY_NEXT
        if service != "running" or not listener_ok
        else None
    )
    return {
        "ok": all(check["status"] == "passed" for check in checks.values()),
        "state": state
        if state in {"invalid", "recovery_required"}
        else "running"
        if all(check["status"] == "passed" for check in checks.values())
        else "degraded",
        "next": next_command,
        "checks": checks,
    }


def _render(command: str, result: CommandResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True))
        return
    rendered = presentation.render(command, result)
    if rendered:
        print(rendered)


def _result_code(command: str, result: CommandResult) -> int:
    """Return a stable nonzero diagnostic status without treating it as an exception."""
    return 1 if command == "doctor" and isinstance(result, dict) and not result.get("ok") else 0


def _error(
    message: str,
    *,
    as_json: bool,
    next_command: str = product_identity.command("doctor"),
    code: str = "usage_error",
) -> None:
    if as_json:
        print(
            json.dumps(
                {"error": {"code": code, "message": message, "next": next_command}},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    else:
        print(
            presentation.error(message, next_command=next_command),
            file=sys.stderr,
        )


def _execute(command: str, *, as_json: bool = False, **arguments: object) -> int:
    try:
        result = dispatch(command, **arguments)
    except errors.ProductError as error:
        _error(
            str(error),
            as_json=as_json,
            next_command=error.next_command,
            code=error.code,
        )
        return 2
    _render(command, result, as_json=as_json)
    return _result_code(command, result)


def _app() -> App:
    app = App(
        name=product_identity.COMMAND_NAME,
        help=__doc__,
        version=_release_version,
        print_error=False,
        exit_on_error=False,
        result_action="return_value",
        help_format="rich",
    )

    @app.command(name="install")
    def install_command(
        *,
        asset: Annotated[
            Path,
            Parameter(
                help="Native release archive; sibling manifest, checksums, and signature required.",
            ),
        ],
        trust_anchor: Annotated[
            Path,
            Parameter(
                name="--trust-anchor",
                help="Trusted SSH allowed-signers file.",
            ),
        ],
        json_output: _JSON = False,
        port: _PORT = runtime_context.DEFAULT_PORT,
        timeout_seconds: _TIMEOUT = 30.0,
    ) -> int:
        """Install or upgrade the native user service."""
        return _execute(
            "install",
            asset=asset,
            as_json=json_output,
            trust_anchor=trust_anchor,
            port=port,
            timeout_seconds=timeout_seconds,
        )

    @app.command(name="status")
    def status_command(
        *, json_output: _JSON = False, port: _PORT = runtime_context.DEFAULT_PORT
    ) -> int:
        """Show installed state and listener health."""
        return _execute("status", as_json=json_output, port=port)

    @app.command(name="doctor")
    def doctor(*, json_output: _JSON = False, port: _PORT = runtime_context.DEFAULT_PORT) -> int:
        """Diagnose the installed product without mutation."""
        return _execute("doctor", as_json=json_output, port=port)

    @app.command(name="recover")
    def recover(*, json_output: _JSON = False, port: _PORT = runtime_context.DEFAULT_PORT) -> int:
        """Resolve an interrupted installation transaction."""
        return _execute("recover", as_json=json_output, port=port)

    @app.command(name="reload")
    def reload_command(
        *,
        json_output: _JSON = False,
        port: _PORT = runtime_context.DEFAULT_PORT,
        timeout_seconds: _TIMEOUT = 30.0,
    ) -> int:
        """Transactionally reload the installed service."""
        return _execute("reload", as_json=json_output, port=port, timeout_seconds=timeout_seconds)

    @app.command(name="rollback")
    def rollback_command(
        *,
        json_output: _JSON = False,
        port: _PORT = runtime_context.DEFAULT_PORT,
        timeout_seconds: _TIMEOUT = 30.0,
    ) -> int:
        """Restore the one verified predecessor release."""
        return _execute(
            "rollback",
            as_json=json_output,
            port=port,
            timeout_seconds=timeout_seconds,
        )

    @app.command(name="uninstall")
    def uninstall_command(
        *,
        json_output: _JSON = False,
        port: _PORT = runtime_context.DEFAULT_PORT,
        purge: _PURGE = False,
    ) -> int:
        """Remove the native service and optionally its owned state."""
        return _execute("uninstall", as_json=json_output, port=port, purge=purge)

    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Run one public command without leaking expected exceptions or warnings."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0].startswith("--internal-"):
        return _run_internal(arguments)
    if arguments and not arguments[0].startswith("-") and arguments[0] not in PUBLIC_COMMANDS:
        _error(
            f"unknown command: {arguments[0]}",
            as_json="--json" in arguments,
            next_command=product_identity.command("--help"),
        )
        return 2
    try:
        result = _app()(arguments, console=Console(), error_console=Console(stderr=True))
    except CycloptsError as error:
        command = arguments[0] if arguments and arguments[0] in PUBLIC_COMMANDS else None
        _error(
            str(error),
            as_json="--json" in arguments,
            next_command=product_identity.command(command, "--help")
            if command
            else product_identity.command("--help"),
        )
        return 2
    return result if isinstance(result, int) else 0


def _run_internal(arguments: list[str]) -> int:
    """Dispatch one exact private service role without adding it to public help."""
    if len(arguments) != 1:
        _error("internal service mode accepts no additional arguments", as_json=False)
        return 2
    mode = arguments[0]
    if mode == service_runtime.PREWARM_MODE:
        return 0
    runtime_spec.activate(service_runtime.current_executable())
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
