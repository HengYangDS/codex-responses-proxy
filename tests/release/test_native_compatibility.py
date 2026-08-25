"""Real predecessor-to-candidate native lifecycle compatibility acceptance."""

from __future__ import annotations

import os
import platform
import subprocess
import threading
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from pathlib import PurePosixPath

import pytest

from codex_responses_proxy import product_identity
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config as runtime_config
from tests.release.fixtures import cleanup_runtime
from tests.release.fixtures import native_environment
from tests.release.fixtures import post_response
from tests.release.fixtures import run_command
from tests.release.fixtures import runtime_context_for
from tests.release.fixtures import signed_asset
from tests.service.handoff.fixtures import ScriptedUpstream
from tests.service.handoff.fixtures import free_port
from tests.service.handoff.fixtures import wait_until
from tools.release import signing

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.native_distribution,
]


def _required_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if value is None:
        pytest.skip(f"{variable} is supplied by the release compatibility session")
    return Path(value).resolve(strict=True)


def _version(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    assert len(parts) == 3
    assert all(part.isascii() and part.isdigit() for part in parts)
    major, minor, patch = parts
    return int(major), int(minor), int(patch)


def _runtime_pid(result: Mapping[str, object]) -> int:
    """Return the exact runtime process identity from one lifecycle result."""

    runtime = result.get("runtime")
    assert isinstance(runtime, dict), result
    pid = runtime.get("pid")
    assert type(pid) is int, result
    return pid


def _materialize_native_bundle(candidate: artifact.VerifiedArtifact, output: Path) -> Path:
    """Materialize exact admitted native executable bytes without its provider manifest."""

    output.mkdir()
    for blob in candidate.peek_blobs():
        if blob.path == "providers.toml":
            continue
        relative = PurePosixPath(blob.path)
        assert relative.parts[0] == "bin"
        target = output.joinpath(*relative.parts[1:])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.content)
        target.chmod(0o755 if blob.mode == "100755" else 0o644)
    platform_id = product_identity.native_release_platform(platform.system(), platform.machine())
    executable = output / product_identity.executable_name(
        windows=platform_id.startswith("windows-")
    )
    assert executable.is_file()
    return output


def _supports_stable_prewarm(executable: Path) -> bool:
    """Return whether one native release implements the stable private probe."""

    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [str(executable), "--internal-prewarm"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=environment,
        timeout=120,
    )
    return completed.returncode == 0


def _supports_explicit_rollback(executable: Path) -> bool:
    """Return whether one installed release owns retained-generation finalization."""

    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [str(executable), "rollback", "--help"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=environment,
        timeout=120,
    )
    return completed.returncode == 0


class TestPublishedPredecessorCompatibility:
    """Prove one authentic published predecessor upgrades without traffic loss."""

    def test_real_predecessor_upgrades_to_current_native_candidate(self, tmp_path: Path) -> None:
        current_executable = _required_path("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        current_bundle = _required_path("CODEX_RESPONSES_PROXY_NATIVE_BUNDLE")
        previous_asset = _required_path("CODEX_RESPONSES_PROXY_PREVIOUS_RELEASE_ASSET")
        previous_trust = _required_path("CODEX_RESPONSES_PROXY_PREVIOUS_RELEASE_TRUST_ANCHOR")

        published_predecessor = artifact.admit(
            previous_asset,
            trust_anchor=previous_trust,
        )
        previous_version = published_predecessor.version
        current_version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
        assert _version(previous_version) < _version(current_version)
        previous_bundle = _materialize_native_bundle(
            published_predecessor,
            tmp_path / "published-predecessor-bundle",
        )
        previous_executable = previous_bundle / "codex-responses-proxy"

        published_home = tmp_path / "published-home"
        published_install = tmp_path / "published-payload"
        published_state = tmp_path / "published-state"
        published_home.mkdir()
        published_port = free_port()
        published_context = runtime_context_for(
            published_home,
            published_install,
            published_state,
            published_port,
        )
        published_environment = native_environment(
            published_home,
            published_install,
            published_state,
        )
        with ExitStack() as published_cleanups:
            published_cleanups.callback(cleanup_runtime, published_context)
            installed_published = run_command(
                previous_executable,
                published_environment,
                "install",
                "--asset",
                str(previous_asset),
                "--trust-anchor",
                str(previous_trust),
                "--port",
                str(published_port),
                "--json",
            )
            assert installed_published["state"] == "installed"
            published_status = run_command(
                previous_executable,
                published_environment,
                "status",
                "--port",
                str(published_port),
                "--json",
            )
            assert published_status["release"] == previous_version
            assert (
                run_command(
                    previous_executable,
                    published_environment,
                    "doctor",
                    "--port",
                    str(published_port),
                    "--json",
                )["ok"]
                is True
            )
            run_command(
                previous_executable,
                published_environment,
                "uninstall",
                "--port",
                str(published_port),
                "--purge",
                "--json",
            )
            assert not published_install.exists()
            assert not payload_state.transaction_root(published_context).exists()

        home, install, state = (
            tmp_path / "home",
            tmp_path / "payload",
            tmp_path / "state",
        )
        home.mkdir()
        port = free_port()
        ctx = runtime_context_for(home, install, state, port)
        environment = native_environment(home, install, state)
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
        upstream_url = upstream.base_url().replace("127.0.0.1", "localhost")
        previous_fixture = signed_asset(
            previous_bundle,
            tmp_path / "previous-assets",
            version=previous_version,
            upstream_url=upstream_url,
            key=key,
            trust=trust,
        )
        current_fixture = signed_asset(
            current_bundle,
            tmp_path / "current-assets",
            version=current_version,
            upstream_url=upstream_url,
            key=key,
            trust=trust,
        )
        previous_paths = {blob.path for blob in published_predecessor.peek_blobs()}
        current_paths = {
            blob.path for blob in artifact.admit(current_fixture, trust_anchor=anchor).peek_blobs()
        }

        with ExitStack() as cleanups:
            cleanups.callback(upstream.close)
            cleanups.callback(cleanup_runtime, ctx)

            installed = run_command(
                previous_executable,
                environment,
                "install",
                "--asset",
                str(previous_fixture),
                "--trust-anchor",
                str(anchor),
                "--port",
                str(port),
                "--json",
            )
            assert installed["state"] == "installed"
            before = run_command(
                current_executable,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            assert before["release"] == previous_version
            before_runtime = before.get("runtime")
            assert isinstance(before_runtime, dict)
            previous_pid = before_runtime.get("pid")
            assert type(previous_pid) is int
            upstream.push((200, b'{"id":"before","status":"completed"}'))
            assert post_response(port) == b'{"id":"before","status":"completed"}'

            stream_started = threading.Event()
            normal_started = threading.Barrier(4)
            release = threading.Event()

            def held_stream(handler) -> None:
                stream_started.set()
                release.wait(timeout=60)
                payload = (
                    b'data: {"type":"response.output_text.delta","delta":"held"}\n\n'
                    b'data: {"type":"response.completed"}\n\n'
                )
                handler.send_response(200)
                handler.send_header("Content-Type", "text/event-stream")
                handler.send_header("Content-Length", str(len(payload)))
                handler.end_headers()
                handler.wfile.write(payload)

            def held_response(handler) -> None:
                normal_started.wait(timeout=20)
                release.wait(timeout=60)
                payload = b'{"id":"held","status":"completed"}'
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(payload)))
                handler.end_headers()
                handler.wfile.write(payload)

            upstream.push(held_stream)
            held: dict[str, bytes] = {}
            stream_holder = threading.Thread(
                target=lambda: held.setdefault(
                    "stream", post_response(port, stream=True, timeout=90)
                ),
                daemon=True,
            )
            stream_holder.start()
            assert stream_started.wait(timeout=20)

            holders = []
            for index in range(3):
                upstream.push(held_response)
                holder = threading.Thread(
                    target=lambda slot=index: held.setdefault(
                        f"normal-{slot}", post_response(port, timeout=90)
                    ),
                    daemon=True,
                )
                holders.append(holder)
                holder.start()
            normal_started.wait(timeout=20)
            cleanups.callback(release.set)

            upgrade_arguments = (
                "install",
                "--asset",
                str(current_fixture),
                "--trust-anchor",
                str(anchor),
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )
            if _supports_stable_prewarm(previous_executable):
                upgrade_driver = previous_executable
            else:
                rejected = run_command(
                    previous_executable,
                    environment,
                    *upgrade_arguments,
                    expected=2,
                )
                assert rejected == {
                    "error": {
                        "code": "lifecycle_error",
                        "message": "native bundle prewarm failed",
                        "next": "codex-responses-proxy doctor",
                    }
                }
                assert not payload_state.transaction_root(ctx).exists()
                retained = run_command(
                    previous_executable,
                    environment,
                    "status",
                    "--port",
                    str(port),
                    "--json",
                )
                assert retained["release"] == previous_version
                assert (
                    run_command(
                        previous_executable,
                        environment,
                        "doctor",
                        "--port",
                        str(port),
                        "--json",
                    )["ok"]
                    is True
                )
                upgrade_driver = current_executable
            if not _supports_explicit_rollback(previous_executable):
                upgrade_driver = current_executable

            upgraded = run_command(
                upgrade_driver,
                environment,
                *upgrade_arguments,
            )
            release.set()
            stream_holder.join(timeout=60)
            for holder in holders:
                holder.join(timeout=60)
            assert not stream_holder.is_alive()
            assert all(not holder.is_alive() for holder in holders)
            assert held.get("stream") == (
                b'data: {"type":"response.output_text.delta","delta":"held"}\n\n'
                b'data: {"type":"response.completed"}\n\n'
            )
            assert {held.get(f"normal-{index}") for index in range(3)} == {
                b'{"id":"held","status":"completed"}'
            }
            assert upgraded["state"] == "upgraded"
            assert wait_until(lambda: process.listener_pids(port) == [_runtime_pid(upgraded)], 20)

            after = run_command(
                current_executable,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            assert after["release"] == current_version
            assert after["payload_transaction"] is None
            after_runtime = after.get("runtime")
            assert isinstance(after_runtime, dict), after
            assert after_runtime.get("pid") != previous_pid
            assert (
                run_command(
                    current_executable,
                    environment,
                    "doctor",
                    "--port",
                    str(port),
                    "--json",
                )["ok"]
                is True
            )
            for relative in previous_paths - current_paths:
                assert not install.joinpath(*PurePosixPath(relative).parts).exists()
            upstream.push((200, b'{"id":"after","status":"completed"}'))
            assert post_response(port) == b'{"id":"after","status":"completed"}'

            rolled_back = run_command(
                current_executable,
                environment,
                "rollback",
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )
            assert rolled_back["state"] == "rolled_back"
            assert rolled_back["from_release"] == current_version
            assert rolled_back["to_release"] == previous_version
            assert wait_until(
                lambda: process.listener_pids(port) == [_runtime_pid(rolled_back)], 20
            )
            after_rollback = run_command(
                current_executable,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            assert after_rollback["release"] == previous_version
            assert after_rollback["payload_transaction"] is None
            assert after_rollback["rollback"] == {
                "state": "available",
                "from_release": previous_version,
                "to_release": current_version,
            }
            assert run_command(
                current_executable,
                environment,
                "recover",
                "--port",
                str(port),
                "--json",
            ) == {"state": "not_required"}

            restored = run_command(
                current_executable,
                environment,
                "rollback",
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )
            assert restored["state"] == "rolled_back"
            assert restored["from_release"] == previous_version
            assert restored["to_release"] == current_version
            assert wait_until(lambda: process.listener_pids(port) == [_runtime_pid(restored)], 20)
            restored_status = run_command(
                current_executable,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            assert restored_status["release"] == current_version
            assert restored_status["payload_transaction"] is None

            reloaded = run_command(
                current_executable,
                environment,
                "reload",
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )
            assert reloaded["new_pid"] != after_runtime.get("pid")
            removed = run_command(
                current_executable,
                environment,
                "uninstall",
                "--port",
                str(port),
                "--purge",
                "--json",
            )
            assert removed == {
                "command_removed": True,
                "state": "purged",
                "stopped": 1,
            }
            assert not install.exists()
            assert not payload_state.transaction_root(ctx).exists()
            assert process.listener_pids(runtime_config.DEFAULT_PORT) == canonical_before
