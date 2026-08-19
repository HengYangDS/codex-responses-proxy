"""Alternate-launcher convergence onto one canonical native supervisor."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import process, reconcile
from codex_responses_proxy.service import identity
from tests.lifecycle.fixtures import install_context, install_payload

POSIX_BRIDGE = pytest.mark.skipif(
    os.name == "nt",
    reason="alternate-launcher recovery uses POSIX symbolic-link replacement",
)


class Adapter:
    def __init__(self, configured: str | None) -> None:
        self.configured = configured
        self.installs = 0

    def configured_executable(self, ctx: runtime_context.RuntimeContext) -> str | None:
        del ctx
        return self.configured

    def install(self, ctx: runtime_context.RuntimeContext) -> None:
        self.installs += 1
        self.configured = ctx.executable


def runtime_for(payload: identity.LoadedPayloadIdentity, *, pid: int = 41) -> dict[str, object]:
    return {
        "pid": pid,
        "release": payload.release,
        "serving_payload_sha256": payload.serving_payload_sha256,
        "release_receipt_sha256": payload.release_receipt_sha256,
        "payload_manifest_sha256": payload.manifest_sha256,
        "handoff_protocol_version": 2,
        "handoff_state": "idle",
        "handoff_transaction_id": None,
        "accepting": True,
        "draining": False,
    }


class TestBridge:
    @POSIX_BRIDGE
    def test_prepare_restore_and_finalize_are_exact(self, tmp_path: Path) -> None:
        canonical = tmp_path / "bin" / "codex-responses-proxy"
        alternate = tmp_path / "runtime" / "launcher"
        canonical.parent.mkdir()
        alternate.parent.mkdir()
        canonical.write_bytes(b"native")
        alternate.write_bytes(b"legacy")
        bridge = reconcile._Bridge(alternate, canonical)

        bridge.prepare()
        assert alternate.is_symlink()
        assert alternate.resolve() == canonical.resolve()
        assert bridge.backup.read_bytes() == b"legacy"

        bridge.restore()
        assert alternate.read_bytes() == b"legacy"
        assert not alternate.is_symlink()
        assert not bridge.backup.exists()

        bridge.prepare()
        bridge.finalize()
        assert not alternate.exists()
        assert not bridge.backup.exists()
        assert not alternate.parent.exists()

    def test_prepare_refuses_ambiguous_or_windows_replacement(
        self, tmp_path: Path, *, mocker
    ) -> None:
        canonical = tmp_path / "native"
        alternate = tmp_path / "alternate"
        canonical.write_bytes(b"native")
        alternate.write_bytes(b"legacy")
        bridge = reconcile._Bridge(alternate, canonical)
        bridge.backup.write_bytes(b"unknown")
        with pytest.raises(errors.InstallError, match="backup already exists"):
            bridge.prepare()
        bridge.backup.unlink()
        mocker.patch.object(reconcile.os, "name", "nt")
        with pytest.raises(errors.InstallError, match="unavailable on Windows"):
            bridge.prepare()


class TestDetection:
    def test_detects_only_one_verified_install_owned_alternate_launcher(
        self, tmp_path: Path, subtests, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        payload = identity.committed_payload(Path(ctx.executable))
        assert payload is not None
        runtime = runtime_for(payload)
        alternate = Path(ctx.install_dir, "retired", "launcher")
        alternate.parent.mkdir()
        alternate.write_text("legacy\n", encoding="utf-8")
        adapter = Adapter(str(alternate))
        generation = process.OwnedProcess(41, str(alternate), 7.0)
        mocker.patch.object(reconcile.process, "listener_pids", return_value=[41])
        mocker.patch.object(reconcile.process, "pid_names_path", return_value=True)
        mocker.patch.object(reconcile.process, "capture_generation", return_value=generation)

        detected = reconcile.detect(ctx, runtime, adapter=adapter)

        assert detected == reconcile.AlternateLauncher(ctx, runtime, alternate, generation)

        invalid = (
            (Adapter(str(tmp_path.parent / "external")), runtime),
            (adapter, {**runtime, "release": "wrong"}),
            (adapter, {**runtime, "pid": True}),
        )
        for candidate_adapter, candidate_runtime in invalid:
            with subtests.test(candidate_runtime=candidate_runtime):
                assert reconcile.detect(ctx, candidate_runtime, adapter=candidate_adapter) is None

    def test_current_rebind_requires_the_same_native_listener_after_install(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        payload = identity.committed_payload(Path(ctx.executable))
        assert payload is not None
        runtime = runtime_for(payload)
        adapter = Adapter(str(Path(ctx.install_dir, "retired", "launcher")))
        mocker.patch.object(reconcile.process, "verified_proxy_listener_pids", return_value=[41])

        result = reconcile.current(
            ctx,
            runtime,
            adapter=adapter,
            runtime_reader=lambda _ctx: dict(runtime),
        )

        assert result == runtime
        assert adapter.installs == 1
        assert adapter.configured is not None
        assert os.path.samefile(adapter.configured, ctx.executable)

        adapter.configured = str(Path(ctx.install_dir, "retired", "launcher"))
        with pytest.raises(errors.InstallError, match="listener changed"):
            reconcile.current(
                ctx,
                runtime,
                adapter=adapter,
                runtime_reader=lambda _ctx: {**runtime, "pid": 42},
            )

    @POSIX_BRIDGE
    def test_current_finishes_a_proved_bridge_after_supervisor_retry(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        payload = identity.committed_payload(Path(ctx.executable))
        assert payload is not None
        runtime = runtime_for(payload)
        alternate = Path(ctx.install_dir, "retired", "launcher")
        alternate.parent.mkdir()
        alternate.write_text("old launcher\n", encoding="utf-8")
        bridge = reconcile._Bridge(alternate, Path(ctx.executable))
        bridge.prepare()
        adapter = Adapter(str(alternate))
        mocker.patch.object(reconcile.process, "verified_proxy_listener_pids", return_value=[41])

        assert (
            reconcile.current(
                ctx,
                runtime,
                adapter=adapter,
                runtime_reader=lambda _ctx: dict(runtime),
            )
            == runtime
        )
        assert not alternate.exists()
        assert not bridge.backup.exists()

    def test_current_installs_a_missing_supervisor_around_the_native_listener(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        payload = identity.committed_payload(Path(ctx.executable))
        assert payload is not None
        runtime = runtime_for(payload)
        adapter = Adapter(None)
        mocker.patch.object(reconcile.process, "verified_proxy_listener_pids", return_value=[41])

        assert (
            reconcile.current(
                ctx,
                runtime,
                adapter=adapter,
                runtime_reader=lambda _ctx: dict(runtime),
            )
            == runtime
        )
        assert adapter.installs == 1
        assert adapter.configured == ctx.executable
