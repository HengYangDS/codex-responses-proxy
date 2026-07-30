#!/usr/bin/env python3
"""Verify and transactionally install one fully published proxy release.

The installer contacts both Forge planes, verifies their exact signed tag,
CI, release record, and equal source tree, then admits only immutable runtime
Git blobs into a sealed payload transaction.  It finalizes only after the new
listener proves the expected aggregate, manifest, receipt, and release identity.
It never reads or mutates Codex conversation history or model metadata.
"""

from __future__ import annotations

import os
import sys
import argparse
import subprocess
import glob
import shutil
from pathlib import Path
from typing import cast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codex_dmx_proxy.supervision.select import adapter  # noqa: E402
from codex_dmx_proxy.deployment import apply  # noqa: E402
from codex_dmx_proxy import installation  # noqa: E402
from codex_dmx_proxy import errors  # noqa: E402
from codex_dmx_proxy import python_runtime  # noqa: E402
from codex_dmx_proxy.release import publication  # noqa: E402
from codex_dmx_proxy.release import admission as release_admission  # noqa: E402
from codex_dmx_proxy.release import inventory  # noqa: E402
from codex_dmx_proxy.release import transaction  # noqa: E402
from codex_dmx_proxy.route import management as route_state  # noqa: E402


def _say(msg: str) -> None:
    print(msg, flush=True)


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _codex_running() -> bool:
    """Best-effort check for a running Codex *desktop app* (mac/win)."""
    try:
        if sys.platform == "darwin":
            r = subprocess.run(
                ["pgrep", "-f", "Codex.app/Contents/MacOS/Codex"], capture_output=True, text=True
            )
            return bool(r.stdout.strip())
        if sys.platform.startswith("win"):
            r = subprocess.run(["tasklist"], capture_output=True, text=True)
            return "Codex.exe" in r.stdout
    except Exception:
        pass
    return False


def build_context(
    port: int,
    upstream: str,
    *,
    proxy_log_max_bytes: int = installation.DEFAULT_PROXY_LOG_MAX_BYTES,
    proxy_log_backup_count: int = installation.DEFAULT_PROXY_LOG_BACKUP_COUNT,
    watchdog_log_max_bytes: int = installation.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
    watchdog_log_backup_count: int = installation.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
) -> installation.InstallContext:
    """Build one validated installation context from user-facing arguments."""
    port = installation.validate_port(port)
    upstream = route_state.normalize_upstream_url(upstream)
    proxy_log_max_bytes = installation.validate_log_retention(
        proxy_log_max_bytes,
        name="proxy log max bytes",
        minimum=4 * 1024,
        maximum=64 * 1024 * 1024,
    )
    proxy_log_backup_count = installation.validate_log_retention(
        proxy_log_backup_count,
        name="proxy log backup count",
        minimum=0,
        maximum=10,
    )
    watchdog_log_max_bytes = installation.validate_log_retention(
        watchdog_log_max_bytes,
        name="watchdog log max bytes",
        minimum=4 * 1024,
        maximum=64 * 1024 * 1024,
    )
    watchdog_log_backup_count = installation.validate_log_retention(
        watchdog_log_backup_count,
        name="watchdog log backup count",
        minimum=0,
        maximum=10,
    )
    codex_home = installation.codex_home()
    home = os.path.dirname(codex_home)
    install_dir = os.path.join(codex_home, "dmx-proxy")
    return installation.InstallContext(
        home=home,
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "codex_dmx_proxy", "listener", "entrypoint.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=python_runtime.resolve_python(),
        codex_config=os.path.join(codex_home, "config.toml"),
        log_dir=os.path.join(codex_home, "log"),
        port=port,
        upstream=upstream,
        proxy_log_max_bytes=proxy_log_max_bytes,
        proxy_log_backup_count=proxy_log_backup_count,
        watchdog_log_max_bytes=watchdog_log_max_bytes,
        watchdog_log_backup_count=watchdog_log_backup_count,
    )


def admit_released_payload(
    authority: publication.PublishedRelease,
    *,
    trust_anchor: Path,
) -> release_admission.ReleasedPayload:
    """Admit exact signed HEAD bytes after independent publication was verified."""

    git = shutil.which("git")
    ssh_keygen = shutil.which("ssh-keygen")
    if not git or not ssh_keygen:
        raise errors.InstallError("git and ssh-keygen are required for released-source admission")
    return release_admission.admit(
        HERE,
        payload_paths=inventory.RUNTIME_FILES,
        trust_anchor=trust_anchor,
        publication=authority,
        git_path=Path(git).resolve(),
        ssh_keygen_path=Path(ssh_keygen).resolve(),
    )


def install_release(
    ctx: installation.InstallContext,
    *,
    tag: str,
    gitlab_remote: str,
    gitlab_api_base: str,
    gitlab_repo: str,
    github_remote: str,
    github_repo: str,
    gitlab_anchor: Path,
    github_anchor: Path,
    policy: Path,
    trust_anchor: Path,
    adapter: apply.ServiceAdapter,
    timeout_seconds: float = 30.0,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
    force_v2_bootstrap: bool = False,
    rollback_recovery: bool = False,
) -> dict[str, object]:
    """Compose live publication verification, source admission, and deployment."""

    git = shutil.which("git")
    if not git:
        raise errors.InstallError("git is required for released-source admission")
    release_admission.require_clean_checkout(HERE, git_path=Path(git).resolve())
    authority = publication.verify(
        tag=tag,
        gitlab_remote=gitlab_remote,
        gitlab_api_base=gitlab_api_base,
        gitlab_repo=gitlab_repo,
        github_remote=github_remote,
        github_repo=github_repo,
        gitlab_anchor=gitlab_anchor,
        github_anchor=github_anchor,
        policy_path=policy,
    )
    if rollback_recovery:
        recovery_runtime = apply.read_runtime(ctx)
        if recovery_runtime is None:
            raise errors.InstallError("protocol-v2 recovery requires an available listener")
        apply.prove_v2_listener(ctx, recovery_runtime)
        transaction.rollback_recovery(ctx, runtime=recovery_runtime)
    released = admit_released_payload(authority, trust_anchor=trust_anchor)
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


def wire_config(ctx: installation.InstallContext) -> bool:
    """Point the Codex provider base_url at the local proxy (backup + rewrite)."""
    if not os.path.exists(ctx.codex_config):
        _die(
            f"Codex config not found at {ctx.codex_config}. "
            "Run/launch Codex once first so it creates its config."
        )
    with open(ctx.codex_config, "r", encoding="utf-8") as fh:
        text = fh.read()

    proxy_url = route_state.legacy_dmx_proxy_base_url(ctx.port)
    if route_state.route_authority(ctx) == "aigw":
        _say("  AIGW owns the marked provider projection; leaving config as-is.")
        return True
    current = route_state.read_base_urls(text)
    state = route_state.load_install_state(ctx)
    if state is not None and route_state.route_status(ctx, state) == "enabled":
        _say(f"  managed base_url already points at proxy ({proxy_url}); leaving config as-is.")
        return True

    if proxy_url in current and not any("dmxapi" in u for u in current):
        # Upgrade from pre-state releases without guessing: accept only a backup
        # that deterministically reconstructs the exact current proxy config.
        backups = sorted(glob.glob(f"{ctx.codex_config}.bak-*"), key=os.path.getmtime, reverse=True)
        for backup in backups:
            if not isinstance(backup, str):
                continue
            try:
                with open(backup, "r", encoding="utf-8") as fh:
                    direct_text = fh.read()
            except OSError:
                continue
            enabled_text, changed = route_state.rewrite_base_url(direct_text, "dmxapi", proxy_url)
            if changed and enabled_text == text:
                route_state.write_install_state(
                    ctx,
                    route_state.make_install_state(
                        ctx,
                        backup_path=backup,
                        direct_text=direct_text,
                        enabled_text=enabled_text,
                    ),
                )
                _say(f"  adopted existing proxy route using {os.path.basename(backup)}.")
                return True
        _say(
            "  base_url already points at proxy but no exact managed backup was found; leaving config as-is."
        )
        return False

    new_text, changed = route_state.rewrite_base_url(text, "dmxapi", proxy_url)
    if changed == 0:
        _say(
            "  no dmxapi base_url found to rewrite. If your provider host differs, "
            f'set base_url = "{proxy_url}" manually in {ctx.codex_config}.'
        )
        return False
    backup = route_state.backup_file(ctx.codex_config)
    state = route_state.make_install_state(
        ctx,
        backup_path=backup,
        direct_text=text,
        enabled_text=new_text,
    )
    route_state.write_install_state(ctx, state)
    try:
        route_state._atomic_write_text(ctx.codex_config, new_text)
    except Exception:
        route_state.remove_install_state(ctx)
        raise
    _say(f"  rewrote {changed} base_url -> {proxy_url} (backup: {os.path.basename(backup)})")
    return True


def main() -> None:
    """Verify publication, install its runtime transaction, and optionally route it."""
    ap = argparse.ArgumentParser(description="Install Codex DMX Proxy.")
    ap.add_argument("--port", type=int, default=installation.DEFAULT_PORT)
    ap.add_argument("--upstream", default=installation.DEFAULT_UPSTREAM)
    ap.add_argument(
        "--proxy-log-max-bytes",
        type=int,
        default=installation.DEFAULT_PROXY_LOG_MAX_BYTES,
        help="maximum bytes retained in each proxy log segment",
    )
    ap.add_argument(
        "--proxy-log-backup-count",
        type=int,
        default=installation.DEFAULT_PROXY_LOG_BACKUP_COUNT,
        help="number of rotated proxy log segments to retain",
    )
    ap.add_argument(
        "--watchdog-log-max-bytes",
        type=int,
        default=installation.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
        help="maximum bytes retained in each watchdog log segment",
    )
    ap.add_argument(
        "--watchdog-log-backup-count",
        type=int,
        default=installation.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
        help="number of rotated watchdog log segments to retain",
    )
    ap.add_argument(
        "--skip-config",
        action="store_true",
        help="don't touch config.toml (only place files + service)",
    )
    ap.add_argument("--tag", required=True, help="exact released vMAJOR.MINOR.PATCH tag")
    ap.add_argument("--gitlab-remote", required=True)
    ap.add_argument("--gitlab-api-base", required=True)
    ap.add_argument("--gitlab-repo", required=True)
    ap.add_argument("--github-remote", required=True)
    ap.add_argument("--github-repo", required=True)
    ap.add_argument("--gitlab-anchor", type=Path, required=True)
    ap.add_argument("--github-anchor", type=Path, required=True)
    ap.add_argument(
        "--policy", type=Path, default=Path(HERE) / "packaging/release/publication-policy.toml"
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
            args.upstream,
            proxy_log_max_bytes=args.proxy_log_max_bytes,
            proxy_log_backup_count=args.proxy_log_backup_count,
            watchdog_log_max_bytes=args.watchdog_log_max_bytes,
            watchdog_log_backup_count=args.watchdog_log_backup_count,
        )
    except errors.InstallError as exc:
        _die(str(exc))
    _say(f"Installing codex-dmx-proxy on {sys.platform}")
    _say(f"  python:      {ctx.python}")
    _say(f"  install dir: {ctx.install_dir}")
    _say(f"  codex cfg:   {ctx.codex_config}")
    _say(f"  upstream:    {ctx.upstream}  port: {ctx.port}")
    _say(
        "  log retention: "
        f"proxy={ctx.proxy_log_max_bytes}B x {ctx.proxy_log_backup_count}, "
        f"watchdog={ctx.watchdog_log_max_bytes}B x {ctx.watchdog_log_backup_count}"
    )

    if args.force_legacy_bootstrap and not args.allow_legacy_bootstrap:
        _die("--force-legacy-bootstrap requires --allow-legacy-bootstrap")

    if _codex_running():
        _say(
            "\n  ℹ Codex desktop appears to be running. AIGW-owned routes are left\n"
            "    unchanged. For a proxy-managed direct-route edit, allow the client\n"
            "    to reload its configuration through its normal lifecycle; existing\n"
            "    conversations remain unchanged.\n"
        )

    try:
        result = install_release(
            ctx,
            tag=args.tag,
            gitlab_remote=args.gitlab_remote,
            gitlab_api_base=args.gitlab_api_base,
            gitlab_repo=args.gitlab_repo,
            github_remote=args.github_remote,
            github_repo=args.github_repo,
            gitlab_anchor=args.gitlab_anchor,
            github_anchor=args.github_anchor,
            policy=args.policy,
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
        publication.PublicationError,
        release_admission.ReleaseSourceError,
        OSError,
    ) as exc:
        _die(str(exc))

    if not args.skip_config:
        _say("Wiring Codex config base_url ...")
        wire_config(ctx)
    else:
        _say("Skipping config (per --skip-config)")

    _say(f"Released payload installed through {result['mode']}.")
    _say(
        "Next: inspect `control.py status --json`. Existing conversations remain unchanged; "
        "validate the original conversation separately when the client has reloaded its configuration."
    )


if __name__ == "__main__":
    main()
