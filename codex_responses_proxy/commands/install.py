#!/usr/bin/env python3
"""Verify and transactionally install one signed proxy release source.

The installer consumes one caller-selected release checkout and external trust
anchor.  It admits only immutable blobs from the checkout's signed annotated
release tag into a sealed payload transaction.  Forge publication policy stays
outside installation.  The transaction finalizes only after the new listener
proves the expected aggregate, manifest, receipt, and release identity.  It
never reads or mutates Codex conversation history or model metadata.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import cast

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

from codex_responses_proxy.supervision.select import adapter  # noqa: E402
from codex_responses_proxy.deployment import apply  # noqa: E402
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.runtime import config as runtime_config  # noqa: E402
from codex_responses_proxy import errors  # noqa: E402
from codex_responses_proxy.supervision import python as python_runtime  # noqa: E402
from codex_responses_proxy.release import admission as release_admission  # noqa: E402
from codex_responses_proxy.payload import inventory  # noqa: E402
from codex_responses_proxy.payload import source as payload_source  # noqa: E402
from codex_responses_proxy.payload import transaction  # noqa: E402


def _say(msg: str) -> None:
    print(msg, flush=True)


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def build_context(
    port: int,
    *,
    proxy_log_max_bytes: int = runtime_config.DEFAULT_PROXY_LOG_MAX_BYTES,
    proxy_log_backup_count: int = runtime_config.DEFAULT_PROXY_LOG_BACKUP_COUNT,
    watchdog_log_max_bytes: int = runtime_config.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
    watchdog_log_backup_count: int = runtime_config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
) -> runtime_context.RuntimeContext:
    """Project user-facing arguments into one portable deployment context."""

    return runtime_context.create(
        python=python_runtime.resolve_python(),
        port=port,
        proxy_log_max_bytes=proxy_log_max_bytes,
        proxy_log_backup_count=proxy_log_backup_count,
        watchdog_log_max_bytes=watchdog_log_max_bytes,
        watchdog_log_backup_count=watchdog_log_backup_count,
    )


def admit_released_payload(
    *,
    trust_anchor: Path,
) -> payload_source.ReleasedPayload:
    """Admit exact signed HEAD bytes from one selected release source."""

    git = shutil.which("git")
    ssh_keygen = shutil.which("ssh-keygen")
    if not git or not ssh_keygen:
        raise errors.InstallError("git and ssh-keygen are required for released-source admission")
    return release_admission.admit(
        PRODUCT_ROOT,
        payload_paths=inventory.RUNTIME_FILES,
        trust_anchor=trust_anchor,
        git_path=Path(git).resolve(),
        ssh_keygen_path=Path(ssh_keygen).resolve(),
    )


def install_release(
    ctx: runtime_context.RuntimeContext,
    *,
    trust_anchor: Path,
    adapter: apply.ServiceAdapter,
    timeout_seconds: float = 30.0,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
    force_v2_bootstrap: bool = False,
    rollback_recovery: bool = False,
) -> dict[str, object]:
    """Compose signed-source admission and transactional deployment."""

    git = shutil.which("git")
    if not git:
        raise errors.InstallError("git is required for released-source admission")
    release_admission.require_clean_checkout(PRODUCT_ROOT, git_path=Path(git).resolve())
    if rollback_recovery:
        recovery_runtime = apply.read_runtime(ctx)
        if recovery_runtime is None:
            raise errors.InstallError("protocol-v2 recovery requires an available listener")
        apply.prove_v2_listener(ctx, recovery_runtime)
        transaction.rollback_recovery(ctx, runtime=recovery_runtime)
    released = admit_released_payload(trust_anchor=trust_anchor)
    payload_transaction = transaction.begin_transaction(ctx, released)
    return apply.install(
        ctx,
        payload_transaction,
        adapter=adapter,
        runtime_reader=apply.read_runtime,
        timeout_seconds=timeout_seconds,
        allow_legacy_bootstrap=allow_legacy_bootstrap,
        force_legacy_bootstrap=force_legacy_bootstrap,
        force_v2_bootstrap=force_v2_bootstrap,
    )


def main() -> None:
    """Verify signed release source and install its product-owned runtime."""
    ap = argparse.ArgumentParser(description="Install Codex Responses Proxy.")
    ap.add_argument("--port", type=int, default=runtime_config.DEFAULT_PORT)
    ap.add_argument(
        "--proxy-log-max-bytes",
        type=int,
        default=runtime_config.DEFAULT_PROXY_LOG_MAX_BYTES,
        help="maximum bytes retained in each proxy log segment",
    )
    ap.add_argument(
        "--proxy-log-backup-count",
        type=int,
        default=runtime_config.DEFAULT_PROXY_LOG_BACKUP_COUNT,
        help="number of rotated proxy log segments to retain",
    )
    ap.add_argument(
        "--watchdog-log-max-bytes",
        type=int,
        default=runtime_config.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
        help="maximum bytes retained in each watchdog log segment",
    )
    ap.add_argument(
        "--watchdog-log-backup-count",
        type=int,
        default=runtime_config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
        help="number of rotated watchdog log segments to retain",
    )
    ap.add_argument(
        "--trust-anchor",
        type=Path,
        required=True,
        help="external allowed-signers file for the canonical released checkout",
    )
    ap.add_argument("--timeout-seconds", type=float, default=30.0)
    ap.add_argument(
        "--allow-legacy-bootstrap",
        action="store_true",
        help="authorize the one-time quiet-window replacement of a legacy listener",
    )
    ap.add_argument(
        "--force-legacy-bootstrap",
        action="store_true",
        help="authorize interruption of a verified legacy listener",
    )
    ap.add_argument(
        "--force-v2-bootstrap",
        action="store_true",
        help="authorize interruption of one exact verified protocol-v2 listener",
    )
    ap.add_argument(
        "--rollback-recovery",
        action="store_true",
        help="restore one exact retained recovery transaction before installing this release",
    )
    args = ap.parse_args()

    try:
        service = cast(apply.ServiceAdapter, adapter())
    except errors.UnsupportedPlatform as e:
        _die(str(e))

    try:
        ctx = build_context(
            args.port,
            proxy_log_max_bytes=args.proxy_log_max_bytes,
            proxy_log_backup_count=args.proxy_log_backup_count,
            watchdog_log_max_bytes=args.watchdog_log_max_bytes,
            watchdog_log_backup_count=args.watchdog_log_backup_count,
        )
    except errors.InstallError as exc:
        _die(str(exc))
    _say(f"Installing codex-responses-proxy on {sys.platform}")
    _say(f"  python:      {ctx.python}")
    _say(f"  install dir: {ctx.install_dir}")
    _say(f"  port:        {ctx.port}")
    _say(
        "  log retention: "
        f"proxy={ctx.proxy_log_max_bytes}B x {ctx.proxy_log_backup_count}, "
        f"watchdog={ctx.watchdog_log_max_bytes}B x {ctx.watchdog_log_backup_count}"
    )

    if args.force_legacy_bootstrap and not args.allow_legacy_bootstrap:
        _die("--force-legacy-bootstrap requires --allow-legacy-bootstrap")

    try:
        result = install_release(
            ctx,
            trust_anchor=args.trust_anchor,
            adapter=service,
            timeout_seconds=args.timeout_seconds,
            allow_legacy_bootstrap=args.allow_legacy_bootstrap,
            force_legacy_bootstrap=args.force_legacy_bootstrap,
            force_v2_bootstrap=args.force_v2_bootstrap,
            rollback_recovery=args.rollback_recovery,
        )
    except errors.ManualStartRequired as warning:
        _die(f"service persistence was not established: {warning}")
    except (
        errors.InstallError,
        release_admission.ReleaseSourceError,
        OSError,
    ) as exc:
        _die(str(exc))

    _say(f"Released payload installed through {result['mode']}.")
    _say("Existing conversations remain unchanged.")
    _say(
        "Next: inspect `python3 -m codex_responses_proxy.commands.control status --json`, "
        "then configure clients through their own control plane."
    )


if __name__ == "__main__":
    main()
