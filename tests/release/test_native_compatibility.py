"""Real predecessor-to-candidate native lifecycle compatibility acceptance."""

from __future__ import annotations

import os
import platform
import subprocess
import threading
import urllib.error
from collections.abc import Mapping
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath

import psutil
import pytest

from codex_responses_proxy import product_identity
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import command
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import control as lifecycle_control
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.runtime.process_environment import native_process_environment
from codex_responses_proxy.service.handoff import transaction as handoff_transaction
from tests.release.fixtures import COMMAND_TIMEOUT_SECONDS
from tests.release.fixtures import assert_admitted_payload_identity
from tests.release.fixtures import assert_native_target_absent
from tests.release.fixtures import cleanup_runtime
from tests.release.fixtures import interrupt_native_controller
from tests.release.fixtures import native_service_projection
from tests.release.fixtures import owned_runtime_contexts
from tests.release.fixtures import post_response
from tests.release.fixtures import preserve_native_host_projection
from tests.release.fixtures import run_command
from tests.release.fixtures import runtime_context_for
from tests.release.fixtures import signed_asset
from tests.service.handoff.fixtures import ScriptedUpstream
from tests.service.handoff.fixtures import free_port
from tests.service.handoff.fixtures import wait_until
from tools.release.artifact import signing

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.native_distribution,
    pytest.mark.usefixtures(preserve_native_host_projection.__name__),
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


def _assert_same_runtime_identity(
    command_result: Mapping[str, object],
    observed_status: Mapping[str, object],
) -> None:
    """Prove two observations identify one process serving one payload."""
    command_runtime = command_result.get("runtime")
    observed_runtime = observed_status.get("runtime")
    assert isinstance(command_runtime, dict), command_result
    assert isinstance(observed_runtime, dict), observed_status
    identity_fields = (
        "pid",
        "release",
        "serving_payload_sha256",
        "release_receipt_sha256",
        "payload_manifest_sha256",
    )
    assert {field: command_runtime.get(field) for field in identity_fields} == {
        field: observed_runtime.get(field) for field in identity_fields
    }
    assert observed_runtime.get("accepting") is True


def _wait_for_upgrade_drain(
    future: Future[dict[str, object]],
    ctx: runtime_context.RuntimeContext,
    *,
    predecessor_pid: int,
    predecessor_release: str,
    timeout_seconds: float,
) -> bool:
    """Release held requests after materialization reaches native drain."""

    def draining_or_finished() -> bool:
        runtime = lifecycle_control.read_runtime(ctx)
        return (
            isinstance(runtime, dict)
            and runtime.get("pid") == predecessor_pid
            and runtime.get("release") == predecessor_release
            and runtime.get("accepting") is False
            and runtime.get("draining") is True
        ) or future.done()

    reached = wait_until(draining_or_finished, timeout_seconds)
    if future.done():
        future.result()
    return reached


def test_upgrade_drain_releases_held_requests(tmp_path: Path, *, mocker) -> None:
    """Release held requests once native replacement closes admission."""
    ctx = runtime_context_for(
        tmp_path / "home",
        tmp_path / "payload",
        tmp_path / "state",
        43210,
    )
    future: Future[dict[str, object]] = Future()
    mocker.patch.object(
        lifecycle_control,
        "read_runtime",
        return_value={
            "pid": 1234,
            "release": "3.1.2",
            "accepting": False,
            "draining": True,
        },
    )

    assert _wait_for_upgrade_drain(
        future,
        ctx,
        predecessor_pid=1234,
        predecessor_release="3.1.2",
        timeout_seconds=0.01,
    )


def test_upgrade_drain_waits_through_materialization(tmp_path: Path, *, mocker) -> None:
    """A materialized candidate is not yet at the native drain boundary."""
    ctx = runtime_context_for(
        tmp_path / "home",
        tmp_path / "payload",
        tmp_path / "state",
        43210,
    )
    future: Future[dict[str, object]] = Future()
    mocker.patch.object(
        lifecycle_control,
        "read_runtime",
        side_effect=[
            {
                "pid": 1234,
                "release": "3.1.2",
                "accepting": True,
                "draining": False,
            },
            {
                "pid": 1234,
                "release": "3.1.2",
                "accepting": False,
                "draining": True,
            },
        ],
    )
    mocker.patch(
        "tests.service.handoff.fixtures.time.monotonic",
        side_effect=[0.0, 0.0, 0.2],
    )
    mocker.patch("tests.service.handoff.fixtures.time.sleep")

    assert _wait_for_upgrade_drain(
        future,
        ctx,
        predecessor_pid=1234,
        predecessor_release="3.1.2",
        timeout_seconds=0.2,
    )


def test_runtime_context_uses_the_native_command_projection(tmp_path: Path, *, mocker) -> None:
    """Build release-test paths through the same owner as production."""
    mocker.patch("tests.release.fixtures.platform.system", return_value="Windows")
    home = tmp_path / "home"
    install = tmp_path / "payload"
    ctx = runtime_context_for(home, install, tmp_path / "state", 43210)

    assert PureWindowsPath(ctx.executable) == PureWindowsPath(
        install / "bin" / "codex-responses-proxy.exe"
    )
    assert PureWindowsPath(ctx.command) == PureWindowsPath(
        home / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "codex-responses-proxy.cmd"
    )


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
    platform_id = product_identity.current_native_release_platform()
    executable = output / product_identity.executable_name(
        windows=platform_id.startswith("windows-")
    )
    assert executable.is_file()
    return output


class TestPublishedPredecessorCompatibility:
    """Separate authentic retained assets, old-produced state, and controlled traffic."""

    def test_untouched_published_payload_survives_upgrade_and_rollback(
        self, tmp_path: Path
    ) -> None:
        current_executable = _required_path("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        current_bundle = _required_path("CODEX_RESPONSES_PROXY_NATIVE_BUNDLE")
        previous_asset = _required_path("CODEX_RESPONSES_PROXY_PREVIOUS_RELEASE_ASSET")
        previous_trust = _required_path("CODEX_RESPONSES_PROXY_PREVIOUS_RELEASE_TRUST_ANCHOR")
        predecessor = artifact.admit(previous_asset, trust_anchor=previous_trust)
        current_version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
        assert _version(predecessor.version) < _version(current_version)

        key = tmp_path / "release-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
            timeout=30,
        )
        public_key = key.with_suffix(".pub").read_text(encoding="ascii").strip()
        trust = f'{signing.PRINCIPAL} namespaces="{signing.NAMESPACE}" {public_key}'
        anchor = tmp_path / "allowed-signers"
        anchor.write_text(trust + "\n", encoding="ascii")
        candidate_asset = signed_asset(
            current_bundle,
            tmp_path / "candidate-assets",
            version=current_version,
            upstream_url=None,
            key=key,
            trust=trust,
        )
        candidate = artifact.admit(candidate_asset, trust_anchor=anchor)
        home, install, state = tmp_path / "home", tmp_path / "payload", tmp_path / "state"
        home.mkdir()
        preserved = home / "unrelated.txt"
        preserved.write_bytes(b"Unrelated operator content.\n")
        port = free_port()
        ctx = runtime_context_for(home, install, state, port)
        environment = native_process_environment(
            user_home=home, install_root=install, state_root=state
        )
        isolated_before = native_service_projection(ctx)
        canonical_ctx = runtime_context.create()
        canonical_before = native_service_projection(canonical_ctx)
        listeners_before = process.listener_pids(runtime_config.DEFAULT_PORT)

        with ExitStack() as cleanups:
            cleanups.callback(cleanup_runtime, ctx)
            installed = run_command(
                current_executable,
                environment,
                "install",
                "--asset",
                str(previous_asset),
                "--trust-anchor",
                str(previous_trust),
                "--port",
                str(port),
                "--json",
            )
            assert installed["state"] == "installed"
            before = run_command(
                current_executable, environment, "status", "--port", str(port), "--json"
            )
            assert_admitted_payload_identity(ctx, predecessor, before)
            _assert_same_runtime_identity(installed, before)
            old_runtime = before.get("runtime")
            assert isinstance(old_runtime, dict)
            old_pid = old_runtime.get("pid")
            assert type(old_pid) is int
            old_listener = process.capture_executable(
                old_pid, generation.selected_context(ctx).executable
            )
            assert old_listener is not None

            upgraded = run_command(
                current_executable,
                environment,
                "install",
                "--asset",
                str(candidate_asset),
                "--trust-anchor",
                str(anchor),
                "--port",
                str(port),
                "--json",
            )
            assert upgraded["state"] == "upgraded"
            after = run_command(
                current_executable, environment, "status", "--port", str(port), "--json"
            )
            assert_admitted_payload_identity(ctx, candidate, after)
            _assert_same_runtime_identity(upgraded, after)
            candidate_runtime = after.get("runtime")
            assert isinstance(candidate_runtime, dict)
            assert candidate_runtime["pid"] != old_pid
            assert process.wait_for_exit(old_listener, timeout_seconds=10)
            candidate_pid = candidate_runtime.get("pid")
            assert type(candidate_pid) is int
            candidate_listener = process.capture_executable(
                candidate_pid, generation.selected_context(ctx).executable
            )
            assert candidate_listener is not None
            assert after["payload_transaction"] is None

            rolled_back = run_command(
                current_executable,
                environment,
                "rollback",
                "--to-release",
                predecessor.version,
                "--port",
                str(port),
                "--json",
            )
            assert rolled_back["state"] == "rolled_back"
            restored = run_command(
                current_executable, environment, "status", "--port", str(port), "--json"
            )
            assert_admitted_payload_identity(ctx, predecessor, restored)
            _assert_same_runtime_identity(rolled_back, restored)
            assert process.wait_for_exit(candidate_listener, timeout_seconds=10)
            assert restored["payload_transaction"] is None
            assert preserved.read_bytes() == b"Unrelated operator content.\n"
            generation_contexts = owned_runtime_contexts(ctx)
            run_command(
                current_executable,
                environment,
                "uninstall",
                "--port",
                str(port),
                "--purge",
                "--json",
            )
            assert not install.exists()
            assert not payload_state.transaction_root(ctx).exists()
            assert not payload_state.journal_path(ctx).exists()
            assert_native_target_absent(ctx, generation_contexts)

        assert native_service_projection(ctx) == isolated_before
        assert native_service_projection(canonical_ctx) == canonical_before
        assert process.listener_pids(runtime_config.DEFAULT_PORT) == listeners_before
        assert preserved.read_bytes() == b"Unrelated operator content.\n"

    def test_current_recovery_consumes_unmodified_old_cli_projection(self, tmp_path: Path) -> None:
        current_executable = _required_path("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        previous_asset = _required_path("CODEX_RESPONSES_PROXY_PREVIOUS_RELEASE_ASSET")
        previous_trust = _required_path("CODEX_RESPONSES_PROXY_PREVIOUS_RELEASE_TRUST_ANCHOR")
        predecessor = artifact.admit(previous_asset, trust_anchor=previous_trust)
        previous_bundle = _materialize_native_bundle(predecessor, tmp_path / "old-controller")
        previous_executable = previous_bundle / product_identity.executable_name(
            windows=platform.system() == "Windows"
        )
        home, install, state = tmp_path / "home", tmp_path / "payload", tmp_path / "state"
        home.mkdir()
        preserved = home / "unrelated.txt"
        preserved.write_bytes(b"Unrelated operator content.\n")
        port = free_port()
        ctx = runtime_context_for(home, install, state, port)
        environment = native_process_environment(
            user_home=home, install_root=install, state_root=state
        )
        isolated_before = native_service_projection(ctx)
        canonical_ctx = runtime_context.create()
        canonical_before = native_service_projection(canonical_ctx)
        listeners_before = process.listener_pids(runtime_config.DEFAULT_PORT)

        with ExitStack() as cleanups:
            cleanups.callback(cleanup_runtime, ctx)
            with subprocess.Popen(
                [
                    str(previous_executable),
                    "install",
                    "--asset",
                    str(previous_asset),
                    "--trust-anchor",
                    str(previous_trust),
                    "--port",
                    str(port),
                    "--json",
                ],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as controller:
                parent = process.wait_for_executable(
                    controller.pid, str(previous_executable), roles={"install"}, timeout_seconds=10
                )
                producers = []
                if parent is not None:
                    producers.append(parent)
                    try:
                        descendants = psutil.Process(parent.pid).children(recursive=True)
                    except psutil.NoSuchProcess:
                        descendants = []
                    for child in descendants:
                        owned = process.capture_executable(
                            child.pid, str(previous_executable), roles={"install"}
                        )
                        if owned is not None:
                            producers.append(owned)
                try:
                    assert parent is not None

                    def old_projection_ready() -> bool:
                        pending = payload_state.status(ctx)
                        return (
                            pending is not None
                            and (pending.get("phase") or pending.get("state"))
                            in {"materialized", "activated"}
                        ) or controller.poll() is not None

                    assert wait_until(old_projection_ready, timeout=COMMAND_TIMEOUT_SECONDS)
                finally:
                    interrupt_native_controller(controller, previous_executable, tuple(producers))
                stdout, stderr = controller.communicate(timeout=30)
                assert controller.returncode != 0, stdout.decode(errors="replace")
                assert b"Traceback" not in stderr

            assert process.pids_naming_executable(str(previous_executable), roles={"install"}) == []
            journal = payload_state.read_journal(ctx)
            assert (journal.get("phase") or journal["state"]) in {"materialized", "activated"}
            assert journal["version"] == predecessor.version
            assert journal["receipt_sha256"] == predecessor.receipt_sha256
            old_ctx = generation.context(ctx, str(journal["transaction_id"]))
            assert_admitted_payload_identity(old_ctx, predecessor)
            journal_bytes = payload_state.journal_path(ctx).read_bytes()
            projection_bytes = {
                path: path.read_bytes()
                for directory in (Path(install), payload_state.transaction_root(ctx))
                for path in directory.rglob("*")
                if path.is_file() and not path.is_symlink()
            }
            command_link = os.readlink(ctx.command) if Path(ctx.command).is_symlink() else None
            runtime = lifecycle_control.read_runtime(ctx)
            if runtime is not None:
                assert runtime["release_receipt_sha256"] == predecessor.receipt_sha256
                assert runtime["serving_payload_sha256"] == predecessor.serving_payload_sha256
            assert payload_state.journal_path(ctx).read_bytes() == journal_bytes
            assert all(path.read_bytes() == content for path, content in projection_bytes.items())
            assert (
                os.readlink(ctx.command) if Path(ctx.command).is_symlink() else None
            ) == command_link

            recovered = run_command(
                current_executable, environment, "recover", "--port", str(port), "--json"
            )
            # Native supervision may complete startup after the controller exits.
            # Bind the reported terminal outcome to its actual resulting state,
            # not an instantaneous pre-recovery observation of an absent listener.
            assert recovered.get("state") in {"finalized", "rolled_back"}
            assert recovered == {
                "state": recovered["state"],
                "transaction_id": journal["transaction_id"],
                "version": predecessor.version,
            }
            assert not payload_state.transaction_root(ctx).exists()
            assert not payload_state.journal_path(ctx).exists()
            if recovered["state"] == "finalized":
                after = run_command(
                    current_executable, environment, "status", "--port", str(port), "--json"
                )
                assert_admitted_payload_identity(ctx, predecessor, after)
                generation_contexts = owned_runtime_contexts(ctx)
                run_command(
                    current_executable,
                    environment,
                    "uninstall",
                    "--port",
                    str(port),
                    "--purge",
                    "--json",
                )
            else:
                generation_contexts = (old_ctx,)
                assert not install.exists()
                assert not Path(ctx.command).exists()
                assert not Path(ctx.command).is_symlink()
            assert_native_target_absent(ctx, generation_contexts)
            assert preserved.read_bytes() == b"Unrelated operator content.\n"

        assert native_service_projection(ctx) == isolated_before
        assert native_service_projection(canonical_ctx) == canonical_before
        assert process.listener_pids(runtime_config.DEFAULT_PORT) == listeners_before

    def test_route_controlled_predecessor_preserves_concurrent_traffic(
        self, tmp_path: Path
    ) -> None:
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
        home, install, state = (
            tmp_path / "home",
            tmp_path / "payload",
            tmp_path / "state",
        )
        home.mkdir()
        port = free_port()
        ctx = runtime_context_for(home, install, state, port)
        environment = native_process_environment(
            user_home=home,
            install_root=install,
            state_root=state,
        )
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
                current_executable,
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
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="upgrade-command")
            cleanups.callback(executor.shutdown, wait=True, cancel_futures=True)
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
            upgrade_future = executor.submit(
                run_command,
                current_executable,
                environment,
                *upgrade_arguments,
            )
            assert _wait_for_upgrade_drain(
                upgrade_future,
                ctx,
                predecessor_pid=previous_pid,
                predecessor_release=previous_version,
                timeout_seconds=COMMAND_TIMEOUT_SECONDS,
            )
            release.set()
            stream_holder.join(timeout=60)
            for holder in holders:
                holder.join(timeout=60)
            upgraded = upgrade_future.result(timeout=90)
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
            installed_command = Path(ctx.command)
            control_executable = Path(generation.control_context(ctx).executable)
            assert command.status(installed_command, control_executable)["state"] == "owned"
            after_runtime = after.get("runtime")
            assert isinstance(after_runtime, dict), after
            candidate_pid = after_runtime.get("pid")
            assert type(candidate_pid) is int
            assert after_runtime.get("handoff_capabilities") == [
                handoff_transaction.SELECTED_GENERATION_HANDOFF_CAPABILITY,
                handoff_transaction.ADMISSION_PRESERVING_HANDOFF_CAPABILITY,
            ]
            candidate_counters = after_runtime.get("counters")
            assert isinstance(candidate_counters, dict)
            drain_rejections_before = candidate_counters.get("responses_rejected_while_draining")
            assert type(drain_rejections_before) is int
            _assert_same_runtime_identity(upgraded, after)
            assert candidate_pid != previous_pid
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

            rollback_hold_started = threading.Event()
            rollback_release = threading.Event()
            traffic_stop = threading.Event()
            traffic_bodies: list[bytes] = []
            traffic_failures: list[str] = []

            def held_during_rollback(handler) -> None:
                rollback_hold_started.set()
                rollback_release.wait(timeout=60)
                payload = b'{"id":"rollback-held","status":"completed"}'
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(payload)))
                handler.end_headers()
                handler.wfile.write(payload)

            def exercise_admission() -> None:
                while not traffic_stop.is_set():
                    upstream.push((200, b'{"id":"traffic","status":"completed"}'))
                    try:
                        traffic_bodies.append(post_response(port, timeout=10))
                    except urllib.error.HTTPError as error:  # pragma: no cover - asserted by parent
                        with error:
                            detail = error.read().decode("utf-8", errors="replace")
                        traffic_failures.append(f"HTTP {error.code}: {detail}")
                        return
                    except Exception as error:  # pragma: no cover - asserted by parent
                        traffic_failures.append(f"{error.__class__.__name__}: {error}")
                        return

            upstream.push(held_during_rollback)
            rollback_held: dict[str, bytes] = {}
            rollback_holder = threading.Thread(
                target=lambda: rollback_held.setdefault("body", post_response(port, timeout=90)),
                daemon=True,
            )
            rollback_holder.start()
            cleanups.callback(rollback_release.set)
            assert rollback_hold_started.wait(timeout=20)

            traffic = threading.Thread(target=exercise_admission, daemon=True)
            traffic.start()
            cleanups.callback(traffic_stop.set)
            assert wait_until(lambda: len(traffic_bodies) >= 3, timeout=20)
            completed_before_rollback = len(traffic_bodies)

            rollback_future = executor.submit(
                run_command,
                current_executable,
                environment,
                "rollback",
                "--to-release",
                previous_version,
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )

            def predecessor_serves_new_requests() -> bool:
                runtime = lifecycle_control.read_runtime(ctx)
                return (
                    isinstance(runtime, dict)
                    and runtime.get("pid") != candidate_pid
                    and runtime.get("release") == previous_version
                    and runtime.get("accepting") is True
                    and runtime.get("draining") is False
                )

            assert wait_until(
                predecessor_serves_new_requests,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            assert wait_until(
                lambda: len(traffic_bodies) > completed_before_rollback,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            traffic_stop.set()
            traffic.join(timeout=20)
            rollback_release.set()
            rollback_holder.join(timeout=60)
            rolled_back = rollback_future.result(timeout=90)

            assert not traffic.is_alive()
            assert not rollback_holder.is_alive()
            assert traffic_bodies
            assert set(traffic_bodies) == {b'{"id":"traffic","status":"completed"}'}
            assert traffic_failures == []
            assert rollback_held == {"body": b'{"id":"rollback-held","status":"completed"}'}
            assert rolled_back["state"] == "rolled_back"
            assert rolled_back["from_release"] == current_version
            assert rolled_back["to_release"] == previous_version
            assert Path(generation.control_context(ctx).executable) == control_executable
            assert command.status(installed_command, control_executable)["state"] == "owned"
            after_rollback = run_command(
                installed_command,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            assert after_rollback["release"] == previous_version
            assert after_rollback["payload_transaction"] is None
            _assert_same_runtime_identity(rolled_back, after_rollback)
            predecessor_runtime = after_rollback.get("runtime")
            assert isinstance(predecessor_runtime, dict)
            predecessor_counters = predecessor_runtime.get("counters")
            assert isinstance(predecessor_counters, dict)
            assert (
                predecessor_counters.get("responses_rejected_while_draining")
                == drain_rejections_before
            )
            assert after_rollback["rollback"] == {
                "state": "available",
                "from_release": previous_version,
                "to_release": current_version,
            }
            rollback_selection = generation.read(ctx)
            rollback_runtime = after_rollback.get("runtime")
            assert rollback_selection is not None
            assert isinstance(rollback_runtime, dict)
            repeated = run_command(
                installed_command,
                environment,
                "rollback",
                "--to-release",
                previous_version,
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )
            assert repeated == {"state": "unchanged", "release": previous_version}
            assert generation.read(ctx) == rollback_selection
            repeated_status = run_command(
                installed_command,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            _assert_same_runtime_identity(after_rollback, repeated_status)
            assert run_command(
                installed_command,
                environment,
                "recover",
                "--port",
                str(port),
                "--json",
            ) == {"state": "not_required"}

            restored = run_command(
                installed_command,
                environment,
                "rollback",
                "--to-release",
                current_version,
                "--port",
                str(port),
                "--timeout-seconds",
                "60",
                "--json",
            )
            assert restored["state"] == "rolled_back"
            assert restored["from_release"] == previous_version
            assert restored["to_release"] == current_version
            restored_status = run_command(
                installed_command,
                environment,
                "status",
                "--port",
                str(port),
                "--json",
            )
            assert restored_status["release"] == current_version
            assert restored_status["payload_transaction"] is None
            _assert_same_runtime_identity(restored, restored_status)

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
            owned_contexts = (*owned_runtime_contexts(ctx), ctx)
            removed = run_command(
                current_executable,
                environment,
                "uninstall",
                "--port",
                str(port),
                "--purge",
                "--json",
            )
            assert set(removed) == {"command_removed", "state", "stopped"}
            assert removed["command_removed"] is True
            assert removed["state"] == "purged"
            assert type(removed["stopped"]) is int
            assert removed["stopped"] >= 0
            projection = native_service_projection(ctx)
            assert projection["status"] == "absent"
            assert projection["configured_executable"] is None
            assert all(
                native_service_projection(owned_ctx)["processes"] == []
                for owned_ctx in owned_contexts
            )
            assert not install.exists()
            assert not payload_state.transaction_root(ctx).exists()
            assert process.listener_pids(port) == []
            assert process.listener_pids(runtime_config.DEFAULT_PORT) == canonical_before
