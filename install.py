#!/usr/bin/env python3
"""install.py — set up the Codex dmx-responses-proxy on this machine.

Idempotent, fail-loud, cross-platform (macOS / Linux / Windows). Steps:

  1. Resolve platform + an ABSOLUTE python interpreter (service contexts have no
     shell PATH; a bare "python3" won't resolve).
  2. Locate ~/.codex/config.toml (same path on all three OSes).
  3. Detect a running Codex desktop client (mac/win). An AIGW-owned route is
     left unchanged; a direct-route edit is reported as pending client reload.
  4. Copy proxy + watchdog into ~/.codex/dmx-proxy/.
  5. Point the Codex provider's base_url at the local proxy (backup first;
     TOML-line-aware rewrite, not a fixed-string sed).
  6. Register the watchdog as a login service via the platform adapter.
  7. Verify: probe the port, then GET /v1/models through the proxy.

The proxy passes the Codex Bearer token through untouched, so this installer never
collects or stores an API key.
"""

from __future__ import annotations

import os
import sys
import time
import shutil
from pathlib import Path
import socket
import argparse
import subprocess
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from platform_adapters import pick_adapter, common  # noqa: E402


def _say(msg: str) -> None:
    print(msg, flush=True)


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _codex_running() -> bool:
    """Best-effort check for a running Codex *desktop app* (mac/win)."""
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["pgrep", "-f", "Codex.app/Contents/MacOS/Codex"],
                               capture_output=True, text=True)
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
    proxy_log_max_bytes: int = common.DEFAULT_PROXY_LOG_MAX_BYTES,
    proxy_log_backup_count: int = common.DEFAULT_PROXY_LOG_BACKUP_COUNT,
    watchdog_log_max_bytes: int = common.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
    watchdog_log_backup_count: int = common.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
) -> common.InstallContext:
    port = common.validate_port(port)
    upstream = common.normalize_upstream_url(upstream)
    proxy_log_max_bytes = common.validate_log_retention(
        proxy_log_max_bytes,
        name="proxy log max bytes",
        minimum=4 * 1024,
        maximum=64 * 1024 * 1024,
    )
    proxy_log_backup_count = common.validate_log_retention(
        proxy_log_backup_count,
        name="proxy log backup count",
        minimum=0,
        maximum=10,
    )
    watchdog_log_max_bytes = common.validate_log_retention(
        watchdog_log_max_bytes,
        name="watchdog log max bytes",
        minimum=4 * 1024,
        maximum=64 * 1024 * 1024,
    )
    watchdog_log_backup_count = common.validate_log_retention(
        watchdog_log_backup_count,
        name="watchdog log backup count",
        minimum=0,
        maximum=10,
    )
    codex_home = common.codex_home()
    home = os.path.dirname(codex_home)
    install_dir = os.path.join(codex_home, "dmx-proxy")
    return common.InstallContext(
        home=home,
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "proxy", "dmx_responses_proxy.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=common.resolve_python(),
        codex_config=os.path.join(codex_home, "config.toml"),
        log_dir=os.path.join(codex_home, "log"),
        port=port,
        upstream=upstream,
        proxy_log_max_bytes=proxy_log_max_bytes,
        proxy_log_backup_count=proxy_log_backup_count,
        watchdog_log_max_bytes=watchdog_log_max_bytes,
        watchdog_log_backup_count=watchdog_log_backup_count,
    )


def copy_payload(ctx: common.InstallContext) -> None:
    """Copy the declared runtime payload and remove known superseded artifacts.

    Route state and config are user/runtime state and remain untouched. Retained
    structured logs remain untouched. The two former macOS launchd stdout/stderr
    sinks are exact superseded artifacts: current service definitions route those
    channels to ``/dev/null`` and use the bounded watchdog log instead, so remove
    them without reading or copying their potentially sensitive contents. The
    `tests/` tree was shipped by older deployments but is not executable runtime
    payload; remove that exact obsolete path before writing the manifest.
    """
    shutil.rmtree(os.path.join(ctx.install_dir, "tests"), ignore_errors=True)
    for filename in ("dmx-watchdog.out.log", "dmx-watchdog.err.log"):
        try:
            Path(ctx.log_dir, filename).unlink(missing_ok=True)
        except OSError:
            pass
    for sub in ("proxy", "watchdog", "platform_adapters"):
        src = os.path.join(HERE, sub)
        dst = os.path.join(ctx.install_dir, sub)
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            if name.endswith(".py"):
                shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
    os.makedirs(ctx.log_dir, exist_ok=True)
    for name in ("control.py", "governance.py", "VERSION"):
        shutil.copy2(os.path.join(HERE, name), os.path.join(ctx.install_dir, name))
    common.write_payload_manifest(ctx)


def wire_config(ctx: common.InstallContext) -> bool:
    """Point the Codex provider base_url at the local proxy (backup + rewrite)."""
    if not os.path.exists(ctx.codex_config):
        _die(f"Codex config not found at {ctx.codex_config}. "
             "Run/launch Codex once first so it creates its config.")
    with open(ctx.codex_config, "r", encoding="utf-8") as fh:
        text = fh.read()

    proxy_url = common.proxy_base_url(ctx.port)
    if common.route_authority(ctx) == "aigw":
        _say("  AIGW owns the marked provider projection; leaving config as-is.")
        return True
    current = common.read_base_urls(text)
    state = common.load_install_state(ctx)
    if state is not None and common.route_status(ctx, state) == "enabled":
        _say(f"  managed base_url already points at proxy ({proxy_url}); leaving config as-is.")
        return True

    if proxy_url in current and not any("dmxapi" in u for u in current):
        # Upgrade from pre-state releases without guessing: accept only a backup
        # that deterministically reconstructs the exact current proxy config.
        backups = sorted(glob.glob(f"{ctx.codex_config}.bak-*"), key=os.path.getmtime, reverse=True)
        for backup in backups:
            try:
                with open(backup, "r", encoding="utf-8") as fh:
                    direct_text = fh.read()
            except OSError:
                continue
            enabled_text, changed = common.rewrite_base_url(direct_text, "dmxapi", proxy_url)
            if changed and enabled_text == text:
                common.write_install_state(
                    ctx,
                    common.make_install_state(
                        ctx, backup_path=backup, direct_text=direct_text, enabled_text=enabled_text,
                    ),
                )
                _say(f"  adopted existing proxy route using {os.path.basename(backup)}.")
                return True
        _say("  base_url already points at proxy but no exact managed backup was found; leaving config as-is.")
        return False

    new_text, changed = common.rewrite_base_url(text, "dmxapi", proxy_url)
    if changed == 0:
        _say("  no dmxapi base_url found to rewrite. If your provider host differs, "
             f"set base_url = \"{proxy_url}\" manually in {ctx.codex_config}.")
        return False
    backup = common.backup_file(ctx.codex_config)
    state = common.make_install_state(
        ctx,
        backup_path=backup,
        direct_text=text,
        enabled_text=new_text,
    )
    common.write_install_state(ctx, state)
    try:
        common._atomic_write_text(ctx.codex_config, new_text)
    except Exception:
        common.remove_install_state(ctx)
        raise
    _say(f"  rewrote {changed} base_url -> {proxy_url} (backup: {os.path.basename(backup)})")
    return True


def verify(ctx: common.InstallContext, timeout: float = 20.0) -> bool:
    """Wait for the port, then GET /v1/models through the proxy."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", ctx.port), timeout=2):
                break
        except OSError:
            time.sleep(1)
    else:
        _say(f"  WARNING: nothing listening on 127.0.0.1:{ctx.port} after {timeout:.0f}s")
        return False

    import urllib.request
    import urllib.error
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{ctx.port}/v1/models")
        with opener.open(req, timeout=15) as r:
            _say(f"  proxy /v1/models -> HTTP {r.status}")
            return 200 <= r.status < 500
    except urllib.error.HTTPError as e:
        # Even a 401 proves the proxy is forwarding to upstream (auth is Codex's job).
        _say(f"  proxy /v1/models -> HTTP {e.code} (proxy is forwarding; auth handled by Codex)")
        return True
    except Exception as e:
        _say(f"  WARNING: proxy probe failed: {e}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Install the Codex dmx-responses-proxy.")
    ap.add_argument("--port", type=int, default=common.DEFAULT_PORT)
    ap.add_argument("--upstream", default=common.DEFAULT_UPSTREAM)
    ap.add_argument(
        "--proxy-log-max-bytes",
        type=int,
        default=common.DEFAULT_PROXY_LOG_MAX_BYTES,
        help="maximum bytes retained in each proxy log segment",
    )
    ap.add_argument(
        "--proxy-log-backup-count",
        type=int,
        default=common.DEFAULT_PROXY_LOG_BACKUP_COUNT,
        help="number of rotated proxy log segments to retain",
    )
    ap.add_argument(
        "--watchdog-log-max-bytes",
        type=int,
        default=common.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
        help="maximum bytes retained in each watchdog log segment",
    )
    ap.add_argument(
        "--watchdog-log-backup-count",
        type=int,
        default=common.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
        help="number of rotated watchdog log segments to retain",
    )
    ap.add_argument("--skip-config", action="store_true",
                    help="don't touch config.toml (only place files + service)")
    args = ap.parse_args()

    try:
        adapter = pick_adapter()
    except common.UnsupportedPlatform as e:
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
    except common.InstallError as exc:
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

    if _codex_running():
        _say("\n  ℹ Codex desktop appears to be running. AIGW-owned routes are left\n"
             "    unchanged. For a proxy-managed direct-route edit, allow the client\n"
             "    to reload its configuration through its normal lifecycle; existing\n"
             "    conversations remain unchanged.\n")

    _say("[1/4] copying proxy + watchdog ...")
    copy_payload(ctx)

    if not args.skip_config:
        _say("[2/4] wiring Codex config base_url ...")
        wire_config(ctx)
    else:
        _say("[2/4] skipping config (per --skip-config)")

    _say("[3/4] registering watchdog service ...")
    try:
        adapter.install(ctx)
    except common.ManualStartRequired as w:
        _say(f"  ⚠ {w}")
    except Exception as e:
        _die(f"service registration failed: {e}")

    _say("[4/4] verifying ...")
    ok = verify(ctx)

    _say("\nDone." if ok else "\nInstalled, but verification did not confirm a 2xx/4xx from the proxy.")
    _say("Next: inspect `control.py status --json`. Existing conversations remain unchanged; "
         "validate the original conversation separately when the client has reloaded its configuration.")


if __name__ == "__main__":
    main()
