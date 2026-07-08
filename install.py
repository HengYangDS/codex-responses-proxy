#!/usr/bin/env python3
"""install.py — set up the Codex dmx-responses-proxy on this machine.

Idempotent, fail-loud, cross-platform (macOS / Linux / Windows). Steps:

  1. Resolve platform + an ABSOLUTE python interpreter (service contexts have no
     shell PATH; a bare "python3" won't resolve).
  2. Locate ~/.codex/config.toml (same path on all three OSes).
  3. Warn if the Codex desktop app is running (mac/win) — it caches config and
     will roll back our edit; the user must quit it first.
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
import socket
import argparse
import subprocess

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


def build_context(port: int, upstream: str) -> common.InstallContext:
    home = common.home_dir()
    install_dir = os.path.join(home, common.INSTALL_DIRNAME)
    return common.InstallContext(
        home=home,
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "proxy", "dmx_responses_proxy.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=common.resolve_python(),
        codex_config=common.codex_config_path(),
        log_dir=os.path.join(common.codex_home(), "log"),
        port=port,
        upstream=upstream,
    )


def copy_payload(ctx: common.InstallContext) -> None:
    """Copy proxy/ and watchdog/ into the install dir (overwrite = idempotent)."""
    for sub in ("proxy", "watchdog"):
        src = os.path.join(HERE, sub)
        dst = os.path.join(ctx.install_dir, sub)
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            if name.endswith(".py"):
                shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
    os.makedirs(ctx.log_dir, exist_ok=True)


def wire_config(ctx: common.InstallContext) -> None:
    """Point the Codex provider base_url at the local proxy (backup + rewrite)."""
    if not os.path.exists(ctx.codex_config):
        _die(f"Codex config not found at {ctx.codex_config}. "
             "Run/launch Codex once first so it creates its config.")
    with open(ctx.codex_config, "r", encoding="utf-8") as fh:
        text = fh.read()

    proxy_url = common.proxy_base_url(ctx.port)
    current = common.read_base_urls(text)
    if proxy_url in current and not any("dmxapi" in u for u in current):
        _say(f"  base_url already points at proxy ({proxy_url}); leaving config as-is.")
        return

    new_text, changed = common.rewrite_base_url(text, "dmxapi", proxy_url)
    if changed == 0:
        _say("  no dmxapi base_url found to rewrite. If your provider host differs, "
             f"set base_url = \"{proxy_url}\" manually in {ctx.codex_config}.")
        return
    backup = common.backup_file(ctx.codex_config)
    with open(ctx.codex_config, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    _say(f"  rewrote {changed} base_url -> {proxy_url} (backup: {os.path.basename(backup)})")


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
    ap.add_argument("--skip-config", action="store_true",
                    help="don't touch config.toml (only place files + service)")
    args = ap.parse_args()

    try:
        adapter = pick_adapter()
    except common.UnsupportedPlatform as e:
        _die(str(e))

    ctx = build_context(args.port, args.upstream)
    _say(f"Installing codex-dmx-proxy on {sys.platform}")
    _say(f"  python:      {ctx.python}")
    _say(f"  install dir: {ctx.install_dir}")
    _say(f"  codex cfg:   {ctx.codex_config}")
    _say(f"  upstream:    {ctx.upstream}  port: {ctx.port}")

    if _codex_running():
        _say("\n  ⚠ Codex desktop app appears to be RUNNING. It caches config.toml and\n"
             "    will roll back the base_url edit. Quit Codex fully (⌘Q / close), then\n"
             "    re-run this installer, and start a NEW Codex thread afterward.\n")

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
    except Exception as e:
        _die(f"service registration failed: {e}")

    _say("[4/4] verifying ...")
    ok = verify(ctx)

    _say("\nDone." if ok else "\nInstalled, but verification did not confirm a 2xx/4xx from the proxy.")
    _say("Next: fully quit & reopen the Codex app (mac/win), then start a NEW thread.")


if __name__ == "__main__":
    main()
