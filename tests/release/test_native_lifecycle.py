"""Signed native lifecycle acceptance against one isolated installation."""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import ExitStack
from pathlib import Path

import pytest

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config as runtime_config
from tests.release.fixtures import cleanup_runtime
from tests.release.fixtures import native_environment
from tests.release.fixtures import native_service_projection
from tests.release.fixtures import post_response
from tests.release.fixtures import preserve_native_host_projection
from tests.release.fixtures import run_command
from tests.release.fixtures import runtime_context_for
from tests.release.fixtures import signed_asset
from tests.service.handoff.fixtures import ScriptedUpstream
from tests.service.handoff.fixtures import free_port
from tools.release import signing

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.usefixtures(preserve_native_host_projection.__name__),
    pytest.mark.native_distribution,
]


class TestSignedNativeLifecycle:
    """Prove the public native lifecycle without touching the canonical service."""

    def test_signed_fresh_lifecycle_is_transactional(self, tmp_path: Path) -> None:
        executable_value = os.environ.get("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        assert executable_value is not None, "native executable must be supplied by release session"
        executable = Path(executable_value).resolve(strict=True)
        bundle = executable.parent
        home, install, state = (
            tmp_path / "home",
            tmp_path / "payload",
            tmp_path / "state",
        )
        home.mkdir()
        port = free_port()
        ctx = runtime_context_for(home, install, state, port)
        environment = native_environment(home, install, state)
        assert ctx.service_id != runtime_context.SERVICE_ID
        isolated_before = native_service_projection(ctx)
        assert isolated_before == {
            "service_id": ctx.service_id,
            "status": "absent",
            "configured_executable": None,
            "processes": [],
        }
        canonical_ctx = runtime_context.create()
        canonical_service_before = native_service_projection(canonical_ctx)
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
        current_version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
        current_asset = signed_asset(
            bundle,
            tmp_path / "current-assets",
            version=current_version,
            upstream_url=upstream_url,
            key=key,
            trust=trust,
        )

        with ExitStack() as cleanups:
            cleanups.callback(upstream.close)
            cleanups.callback(cleanup_runtime, ctx)

            installed = run_command(
                executable,
                environment,
                "install",
                "--asset",
                str(current_asset),
                "--trust-anchor",
                str(anchor),
                "--port",
                str(port),
                "--json",
            )
            assert installed["state"] == "installed"
            status = run_command(executable, environment, "status", "--port", str(port), "--json")
            assert status["release"] == current_version
            assert status["service"] == "running"
            installed_runtime = installed.get("runtime")
            assert isinstance(installed_runtime, dict)
            installed_pid = installed_runtime.get("pid")
            assert type(installed_pid) is int
            assert (
                run_command(executable, environment, "doctor", "--port", str(port), "--json")["ok"]
                is True
            )
            upstream.push((200, b'{"id":"ok","status":"completed"}'))
            assert post_response(port) == b'{"id":"ok","status":"completed"}'
            assert (
                run_command(executable, environment, "reload", "--port", str(port), "--json")[
                    "new_pid"
                ]
                != installed_pid
            )
            run_command(
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
            recovered = run_command(
                executable, environment, "recover", "--port", str(port), "--json"
            )
            assert recovered == {
                "state": "closed",
                "transaction_id": "fixture-prepared",
                "version": current_version,
            }
            assert not transaction_root.exists()
        assert native_service_projection(ctx) == isolated_before
        assert native_service_projection(canonical_ctx) == canonical_service_before
        assert process.listener_pids(runtime_config.DEFAULT_PORT) == canonical_before

    @pytest.mark.parametrize("interruption", [AssertionError, TimeoutError, KeyboardInterrupt])
    def test_native_teardown_survives_test_control_flow_failures(
        self,
        tmp_path: Path,
        interruption: type[BaseException],
    ) -> None:
        """Leave no native service behind when a test aborts after installation."""

        executable_value = os.environ.get("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        assert executable_value is not None, "native executable must be supplied by release session"
        executable = Path(executable_value).resolve(strict=True)
        home, install, state = (
            tmp_path / "home",
            tmp_path / "payload",
            tmp_path / "state",
        )
        home.mkdir()
        port = free_port()
        ctx = runtime_context_for(home, install, state, port)
        environment = native_environment(home, install, state)
        isolated_before = native_service_projection(ctx)
        canonical_ctx = runtime_context.create()
        canonical_before = native_service_projection(canonical_ctx)

        key = tmp_path / "release-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
        )
        public_key = key.with_suffix(".pub").read_text(encoding="ascii").strip()
        trust = f'{signing.PRINCIPAL} namespaces="{signing.NAMESPACE}" {public_key}'
        anchor = tmp_path / "allowed-signers"
        anchor.write_text(trust + "\n", encoding="ascii")
        current_version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
        current_asset = signed_asset(
            executable.parent,
            tmp_path / "current-assets",
            version=current_version,
            upstream_url="http://127.0.0.1:1",
            key=key,
            trust=trust,
        )

        def interrupt_installed_lifecycle() -> None:
            with ExitStack() as cleanups:
                cleanups.callback(cleanup_runtime, ctx)
                installed = run_command(
                    executable,
                    environment,
                    "install",
                    "--asset",
                    str(current_asset),
                    "--trust-anchor",
                    str(anchor),
                    "--port",
                    str(port),
                    "--json",
                )
                assert installed["state"] == "installed"
                raise interruption("simulated test control-flow failure")

        with pytest.raises(interruption):
            interrupt_installed_lifecycle()

        assert native_service_projection(ctx) == isolated_before
        assert native_service_projection(canonical_ctx) == canonical_before
