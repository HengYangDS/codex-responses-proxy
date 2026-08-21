"""Real predecessor-to-candidate native lifecycle compatibility acceptance."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

import pytest

from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config as runtime_config
from tests.release.fixtures import (
    cleanup_runtime,
    native_environment,
    post_response,
    run_command,
    runtime_context_for,
    signed_asset,
)
from tests.service.handoff.fixtures import ScriptedUpstream, free_port
from tools.release import signing

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.native_distribution,
    pytest.mark.skipif(sys.platform != "darwin", reason="native upgrade acceptance is macOS-only"),
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
    executable = output / "codex-responses-proxy"
    assert executable.is_file()
    return output


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
            assert installed_published["mode"] == "fresh-install"
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
            assert installed["mode"] == "fresh-install"
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

            upgraded = run_command(
                previous_executable,
                environment,
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
            assert upgraded["mode"] == "upgrade"

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
            assert isinstance(after_runtime, dict)
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
            assert removed == {"command_removed": True, "purged": True, "stopped": 1}
            assert not install.exists()
            assert not payload_state.transaction_root(ctx).exists()
            assert process.listener_pids(runtime_config.DEFAULT_PORT) == canonical_before
