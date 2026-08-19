"""Signed macOS lifecycle acceptance against one isolated native installation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import pytest

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import macos, process
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import inventory
from tests.service.handoff.fixtures import ScriptedUpstream, free_port, wait_until
from tools.release import assets as release_assembly
from tools.release import product_assets, signing

ROOT = Path(__file__).resolve().parents[2]
COMMAND_TIMEOUT_SECONDS = 180

pytestmark = [
    pytest.mark.native_distribution,
    pytest.mark.skipif(
        sys.platform != "darwin", reason="alternate launcher incident is macOS-only"
    ),
]


def _previous_patch(version: str) -> str:
    major, minor, patch = map(int, version.split("."))
    if patch <= 0:
        raise AssertionError("native lifecycle acceptance requires a positive patch release")
    return f"{major}.{minor}.{patch - 1}"


def _run(
    executable: Path,
    environment: dict[str, str],
    *arguments: str,
    expected: int = 0,
) -> dict[str, object]:
    result = subprocess.run(
        [str(executable), *arguments],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == expected, result.stderr or result.stdout
    assert "Traceback" not in result.stderr
    assert "Warning" not in result.stderr
    output = result.stdout if result.stdout else result.stderr
    value = json.loads(output)
    assert isinstance(value, dict)
    return value


def _signed_asset(
    bundle: Path,
    output: Path,
    *,
    version: str,
    upstream_url: str,
    key: Path,
    trust: str,
) -> Path:
    platform_id = "macos-arm64"
    executable = bundle / "codex-responses-proxy"
    files: dict[str, bytes | product_assets.ArchiveFile] = {
        "bin/codex-responses-proxy": product_assets.ArchiveFile(executable.read_bytes(), 0o755),
        "providers.toml": (
            f'version = 1\n\n[providers.dmxapi]\nbase_url = "{upstream_url}"\npolicy = "dmxapi"\n'
        ).encode(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
    }
    for relative, source in release_assembly._bundle_files(bundle):
        if relative == Path(executable.name):
            continue
        files[f"bin/{relative.as_posix()}"] = source.read_bytes()
    archive_name = product_assets.archive_name(version, platform_id)
    archive = product_assets.archive_bytes(files, version, platform_id)
    manifest_name = product_assets.manifest_name(platform_id)
    manifest = product_assets.asset_manifest(
        version=version,
        platform=platform_id,
        archive_name=archive_name,
        archive=archive,
        files=files,
    )
    output.mkdir()
    release_files = {archive_name: archive, manifest_name: manifest}
    for name, content in {
        **release_files,
        product_assets.CHECKSUM_NAME: product_assets.checksums(release_files),
    }.items():
        (output / name).write_bytes(content)
    signing.sign_and_verify(assets=output, key=key, trust=trust)
    return output / archive_name


def _wrapper(path: Path, *, source: Path, installed: Path, python: Path) -> None:
    path.write_text(
        f"""#!{python}
from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

SOURCE = Path({str(source)!r})
INSTALLED_EXECUTABLE = Path({str(installed)!r})
RUNTIME_EXECUTABLE = Path(__file__).resolve()
sys.path.insert(0, str(SOURCE))


def run_listener() -> int:
    from codex_responses_proxy.service import entrypoint, identity, runtime

    runtime.current_executable = lambda: str(INSTALLED_EXECUTABLE)
    installed_context = entrypoint._handoff_context

    def alternate_context():
        return replace(
            installed_context(),
            executable=RUNTIME_EXECUTABLE,
            committed_payload=lambda: identity.committed_payload(INSTALLED_EXECUTABLE),
        )

    entrypoint._handoff_context = alternate_context
    return entrypoint.run(
        handoff_child=(
            "--internal-handoff-child" in sys.argv
            or os.environ.get("CODEX_RESPONSES_PROXY_HANDOFF_CHILD") == "1"
        )
    )


def run_watchdog() -> int:
    from codex_responses_proxy.lifecycle.supervision import watchdog

    watchdog.EXECUTABLE = str(RUNTIME_EXECUTABLE)
    watchdog.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(
        run_watchdog() if "--internal-watchdog" in sys.argv else run_listener()
    )
""",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _post(port: int, *, timeout: float = 15) -> bytes:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/dmxapi/v1/responses",
        data=b'{"stream": false, "input": []}',
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def _context(home: Path, install: Path, state: Path, port: int) -> runtime_context.RuntimeContext:
    return runtime_context.RuntimeContext(
        home=str(home),
        install_dir=str(install),
        executable=inventory.installed_executable(str(install)),
        command=str(home / ".local/bin/codex-responses-proxy"),
        log_dir=str(state),
        port=port,
    )


def _load_alternate_service(
    ctx: runtime_context.RuntimeContext,
    wrapper: Path,
) -> Path:
    alternate = replace(ctx, executable=str(wrapper))
    plist = Path(ctx.home, "Library/LaunchAgents", f"{ctx.service_id}.plist")
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(macos.render_plist(alternate), encoding="utf-8")
    subprocess.run(["plutil", "-lint", str(plist)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["launchctl", "load", "-w", str(plist)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return plist


def _cleanup(ctx: runtime_context.RuntimeContext, wrapper: Path) -> None:
    plist = Path(ctx.home, "Library/LaunchAgents", f"{ctx.service_id}.plist")
    if plist.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        plist.unlink(missing_ok=True)
    for pid in process.pids_naming_path(str(wrapper)):
        process.terminate_pid(pid, expected_path=str(wrapper))
    roles = {"--internal-listener", "--internal-handoff-child", "--internal-watchdog"}
    for pid in process.pids_naming_executable(ctx.executable, roles=roles):
        process.terminate_executable(pid, ctx.executable, roles=roles)


class TestSignedNativeLifecycle:
    """Prove the public native lifecycle without touching the canonical service."""

    def test_signed_alternate_root_lifecycle_is_transactional(self, tmp_path: Path) -> None:
        executable_value = os.environ.get("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        if executable_value is None:
            pytest.skip("native executable supplied by release session")
        executable = Path(executable_value).resolve(strict=True)
        bundle = executable.parent
        home, install, state = tmp_path / "home", tmp_path / "payload", tmp_path / "state"
        home.mkdir()
        port = free_port()
        ctx = _context(home, install, state, port)
        wrapper = install / "runtime-legacy/codex-responses-proxy-runtime"
        environment = {
            "CODEX_RESPONSES_PROXY_HOME": str(install),
            "CODEX_RESPONSES_PROXY_STATE_HOME": str(state),
            "HOME": str(home),
            "PATH": os.pathsep.join(("/usr/bin", "/bin", "/usr/sbin", "/sbin")),
            "PYTHONNOUSERSITE": "1",
            "USERPROFILE": str(home),
        }
        canonical_before = process.listener_pids(runtime_config.DEFAULT_PORT)

        key = tmp_path / "release-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
        )
        public_key = key.with_suffix(".pub").read_text(encoding="ascii").strip()
        trust = f'{signing.PRINCIPAL} namespaces="{signing.NAMESPACE}" {public_key}'
        anchor = tmp_path / "allowed-signers"
        anchor.write_text(trust + "\n", encoding="ascii")

        upstream = ScriptedUpstream()
        upstream.start()
        current_version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
        old_version = _previous_patch(current_version)
        old_asset = _signed_asset(
            bundle,
            tmp_path / "old-assets",
            version=old_version,
            upstream_url=upstream.base_url(),
            key=key,
            trust=trust,
        )
        current_asset = _signed_asset(
            bundle,
            tmp_path / "current-assets",
            version=current_version,
            upstream_url=upstream.base_url(),
            key=key,
            trust=trust,
        )

        with ExitStack() as cleanups:
            cleanups.callback(upstream.close)
            cleanups.callback(_cleanup, ctx, wrapper)

            installed = _run(
                executable,
                environment,
                "install",
                "--asset",
                str(old_asset),
                "--trust-anchor",
                str(anchor),
                "--port",
                str(port),
                "--json",
            )
            assert installed["mode"] == "fresh-install"
            status = _run(executable, environment, "status", "--port", str(port), "--json")
            assert status["release"] == old_version
            assert status["service"] == "running"
            installed_runtime = installed.get("runtime")
            assert isinstance(installed_runtime, dict)
            installed_pid = installed_runtime.get("pid")
            assert type(installed_pid) is int
            assert (
                _run(executable, environment, "doctor", "--port", str(port), "--json")["ok"] is True
            )
            assert (
                _run(executable, environment, "reload", "--port", str(port), "--json")["new_pid"]
                != installed_pid
            )

            _run(executable, environment, "uninstall", "--port", str(port), "--json")
            wrapper.parent.mkdir()
            _wrapper(
                wrapper,
                source=ROOT / "src",
                installed=Path(ctx.executable),
                python=Path(sys.executable).resolve(),
            )
            plist = _load_alternate_service(ctx, wrapper)
            assert wait_until(lambda: process.listener_pids(port), timeout=60)
            assert macos.configured_executable(ctx) == str(wrapper)

            started, release = threading.Event(), threading.Event()

            def held_response(handler) -> None:
                started.set()
                release.wait(timeout=30)
                payload = b'{"id":"held","status":"completed"}'
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(payload)))
                handler.end_headers()
                handler.wfile.write(payload)

            upstream.push(held_response)
            held: dict[str, bytes] = {}
            holder = threading.Thread(
                target=lambda: held.setdefault("body", _post(port, timeout=60))
            )
            holder.start()
            cleanups.callback(release.set)
            assert started.wait(timeout=15)

            upgraded = _run(
                executable,
                environment,
                "install",
                "--asset",
                str(current_asset),
                "--trust-anchor",
                str(anchor),
                "--port",
                str(port),
                "--timeout-seconds",
                "30",
                "--json",
            )
            release.set()
            holder.join(timeout=30)
            assert held.get("body") == b'{"id":"held","status":"completed"}'
            assert upgraded["mode"] == "upgrade"
            assert not wrapper.exists()
            assert not wrapper.with_name(f".{wrapper.name}.native-reconcile").exists()
            assert macos.configured_executable(ctx) == ctx.executable
            assert plist.is_file()

            status = _run(executable, environment, "status", "--port", str(port), "--json")
            assert status["release"] == current_version
            assert status["payload_transaction"] is None
            assert (
                _run(executable, environment, "doctor", "--port", str(port), "--json")["ok"] is True
            )
            _run(executable, environment, "reload", "--port", str(port), "--json")
            _run(
                executable,
                environment,
                "uninstall",
                "--port",
                str(port),
                "--purge",
                "--json",
            )
            assert not install.exists()

            transaction_root = payload_state.transaction_root(ctx)
            transaction_root.mkdir()
            (transaction_root / payload_state.TRANSACTION_JOURNAL_FILENAME).write_text(
                json.dumps(
                    {
                        "fresh": True,
                        "receipt_sha256": "0" * 64,
                        "schema_version": payload_state.TRANSACTION_JOURNAL_SCHEMA,
                        "state": "prepared",
                        "transaction_id": "fixture-prepared",
                        "version": current_version,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            recovered = _run(executable, environment, "recover", "--port", str(port), "--json")
            assert recovered == {
                "state": "closed",
                "transaction_id": "fixture-prepared",
                "version": current_version,
            }
            assert not transaction_root.exists()
            assert process.listener_pids(runtime_config.DEFAULT_PORT) == canonical_before
