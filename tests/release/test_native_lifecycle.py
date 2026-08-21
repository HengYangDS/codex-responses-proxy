"""Signed macOS lifecycle acceptance against one isolated native installation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

import pytest

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
from tests.release.fixtures import (
    preserve_native_host_projection as preserve_native_host_projection,
)
from tests.service.handoff.fixtures import ScriptedUpstream, free_port
from tools.release import signing

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.native_distribution,
    pytest.mark.skipif(
        sys.platform != "darwin", reason="native lifecycle acceptance is macOS-only"
    ),
]


class TestSignedNativeLifecycle:
    """Prove the public native lifecycle without touching the canonical service."""

    def test_signed_fresh_lifecycle_is_transactional(self, tmp_path: Path) -> None:
        executable_value = os.environ.get("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        if executable_value is None:
            pytest.skip("native executable supplied by release session")
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
            assert installed["mode"] == "fresh-install"
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
            assert process.listener_pids(runtime_config.DEFAULT_PORT) == canonical_before
