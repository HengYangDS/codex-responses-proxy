#!/usr/bin/env python3
"""Remove the product-owned Codex Responses Proxy service and payload."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Protocol, cast

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.supervision import process  # noqa: E402
from codex_responses_proxy.payload import projection  # noqa: E402
from codex_responses_proxy.supervision.select import adapter  # noqa: E402


class ServiceAdapter(Protocol):
    """Native supervision operations required by uninstall."""

    def uninstall(self, ctx: runtime_context.RuntimeContext) -> None: ...

    def status(self, ctx: runtime_context.RuntimeContext) -> str: ...


def _say(message: str) -> None:
    print(message, flush=True)


def _context(port: int = runtime_context.DEFAULT_PORT) -> runtime_context.RuntimeContext:
    """Project the installed product without consulting client configuration."""

    return runtime_context.create(python=sys.executable, port=port)


def _stop_proxy(ctx: runtime_context.RuntimeContext) -> int:
    """Terminate and prove exit of each listener owned by this installation."""

    pids = process.verified_proxy_listener_pids(ctx)
    for pid in pids:
        if not process.terminate_pid(pid, expected_path=ctx.proxy_script):
            raise errors.InstallError(f"verified proxy listener {pid} did not exit")
    if remaining := process.verified_proxy_listener_pids(ctx):
        raise errors.InstallError(f"verified proxy listeners remain: {remaining}")
    return len(pids)


def _remove_service(service: ServiceAdapter, ctx: runtime_context.RuntimeContext) -> None:
    """Deregister supervision and require its read-only status to prove absence."""

    service.uninstall(ctx)
    if (state := service.status(ctx)) != "absent":
        raise errors.InstallError(f"watchdog service remains {state}")


def main() -> None:
    """Remove native supervision and optionally purge the manifest-owned payload."""

    parser = argparse.ArgumentParser(description="Uninstall Codex Responses Proxy.")
    parser.add_argument("--port", type=int, default=runtime_context.DEFAULT_PORT)
    parser.add_argument(
        "--purge",
        action="store_true",
        help="also remove the manifest-owned runtime payload; preserve unknown content",
    )
    args = parser.parse_args()
    try:
        ctx = _context(args.port)
        service = cast(ServiceAdapter, adapter())
    except (errors.InstallError, errors.UnsupportedPlatform) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    _say("Uninstalling codex-responses-proxy ...")
    _say("[1/2] deregistering watchdog service and listener ...")
    try:
        _remove_service(service, ctx)
        _stop_proxy(ctx)
    except (errors.InstallError, OSError) as exc:
        raise SystemExit(f"ERROR: uninstall stopped before payload mutation: {exc}") from exc

    if args.purge:
        _say("[2/2] removing manifest-owned payload ...")
        try:
            remaining = projection.purge_installed_projection(ctx)
        except errors.InstallError as exc:
            raise SystemExit(f"ERROR: payload purge refused: {exc}") from exc
        if remaining:
            raise SystemExit(
                "ERROR: manifest-owned payload was removed, but unknown install content remains: "
                + ", ".join(remaining)
            )
    else:
        _say(f"[2/2] leaving install dir {ctx.install_dir} (use --purge to delete)")

    _say("Done. Client endpoint configuration was not read or changed.")


if __name__ == "__main__":
    main()
