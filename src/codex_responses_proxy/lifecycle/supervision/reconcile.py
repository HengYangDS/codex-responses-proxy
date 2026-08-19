"""Converge a verified alternate launcher onto the canonical native executable."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import runtime as service_runtime

RuntimeReader = Callable[[runtime_context.RuntimeContext], dict[str, object] | None]


class ServiceAdapter(Protocol):
    """Native supervisor projection needed for launcher convergence."""

    def install(self, ctx: runtime_context.RuntimeContext) -> None: ...

    def configured_executable(self, ctx: runtime_context.RuntimeContext) -> str | None: ...


@dataclass(frozen=True, slots=True)
class AlternateLauncher:
    """Exact noncanonical launcher and live process generation to retire."""

    context: runtime_context.RuntimeContext
    current: dict[str, object]
    executable: Path
    listener: process.OwnedProcess

    def migrate(
        self,
        *,
        adapter: ServiceAdapter,
        runtime_reader: RuntimeReader,
        timeout_seconds: float,
    ) -> dict[str, object]:
        """Handoff the current payload, then rebind its native supervisor."""

        bridge = _Bridge(self.executable, Path(self.context.executable))
        bridge.prepare()
        expected = handoff.expected_metadata(self.context.install_dir)
        try:
            runtime = _request(
                self.context,
                expected,
                current=self.current,
                listener=self.listener,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
            )
        except BaseException:
            bridge.restore()
            raise
        try:
            adapter.install(self.context)
            configured = adapter.configured_executable(self.context)
            if configured is None or not _same_path(configured, self.context.executable):
                raise errors.InstallError("native supervisor did not bind the canonical executable")
        except BaseException as error:
            raise errors.InstallError(
                "listener is native but supervisor reconciliation is incomplete; retry install"
            ) from error
        bridge.finalize()
        return runtime


def current(
    ctx: runtime_context.RuntimeContext,
    runtime: Mapping[str, object],
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
) -> dict[str, object]:
    """Rebind a stale supervisor around an already canonical listener."""

    configured = adapter.configured_executable(ctx)
    if configured is not None and _declares_path(configured, ctx.executable):
        return dict(runtime)
    bridge = _prepared_bridge(configured, ctx.executable) if configured is not None else None
    pid = runtime.get("pid")
    committed = identity.committed_payload(Path(ctx.executable))
    if (
        type(pid) is not int
        or committed is None
        or process.verified_proxy_listener_pids(ctx) != [pid]
        or not _runtime_matches(runtime, committed)
    ):
        raise errors.InstallError("stale supervisor is not bound to a verified native listener")
    adapter.install(ctx)
    rebound = adapter.configured_executable(ctx)
    if rebound is None or not _same_path(rebound, ctx.executable):
        raise errors.InstallError("native supervisor did not bind the canonical executable")
    observed = runtime_reader(ctx)
    if (
        not isinstance(observed, dict)
        or observed.get("pid") != pid
        or process.verified_proxy_listener_pids(ctx) != [pid]
        or not _runtime_matches(observed, committed)
    ):
        raise errors.InstallError("native listener changed during supervisor reconciliation")
    if bridge is not None:
        bridge.finalize()
    return observed


@dataclass(frozen=True, slots=True)
class _Bridge:
    alternate: Path
    canonical: Path

    @property
    def backup(self) -> Path:
        return self.alternate.with_name(f".{self.alternate.name}.native-reconcile")

    def prepare(self) -> None:
        """Atomically make the retired launcher resolve to the native payload."""

        if os.name == "nt":
            raise errors.InstallError(
                "alternate launcher reconciliation is unavailable on Windows; uninstall it first"
            )
        if self.alternate.is_symlink() and _same_path(self.alternate, self.canonical):
            if self.backup.is_file():
                return
            raise errors.InstallError("alternate launcher bridge has no retained original")
        if self.backup.exists() or self.backup.is_symlink():
            raise errors.InstallError("alternate launcher backup already exists")
        if not self.alternate.is_file() or self.alternate.is_symlink():
            raise errors.InstallError("alternate launcher is not one replaceable file")
        os.replace(self.alternate, self.backup)
        try:
            os.symlink(self.canonical, self.alternate)
        except BaseException:
            os.replace(self.backup, self.alternate)
            raise

    def restore(self) -> None:
        """Restore the exact launcher only after a proved handoff rollback."""

        if self.alternate.is_symlink() and _same_path(self.alternate, self.canonical):
            self.alternate.unlink()
        if self.backup.is_file() and not self.alternate.exists():
            os.replace(self.backup, self.alternate)

    def finalize(self) -> None:
        """Delete the retired launcher after native supervision is proven."""

        if not self.alternate.is_symlink() or not _same_path(self.alternate, self.canonical):
            raise errors.InstallError("alternate launcher bridge changed before finalization")
        self.alternate.unlink()
        self.backup.unlink()
        _remove_empty_launcher_directories(self.alternate.parent, self.canonical.parents[1])


def detect(
    ctx: runtime_context.RuntimeContext,
    current: Mapping[str, object],
    *,
    adapter: ServiceAdapter,
) -> AlternateLauncher | None:
    """Return one strictly proved alternate launcher, never a compatibility guess."""

    pid = current.get("pid")
    if type(pid) is not int or pid <= 0:
        return None
    committed = identity.committed_payload(Path(ctx.executable))
    if committed is None or not _runtime_matches(current, committed):
        return None
    configured = adapter.configured_executable(ctx)
    if configured is None or _same_path(configured, ctx.executable):
        return None
    alternate = Path(configured)
    try:
        alternate.resolve(strict=True).relative_to(Path(ctx.install_dir).resolve(strict=True))
    except (OSError, ValueError):
        return None
    if process.listener_pids(ctx.port) != [pid]:
        return None
    roles = {service_runtime.LISTENER_MODE, service_runtime.HANDOFF_CHILD_MODE}
    if not (
        process.pid_names_path(pid, configured)
        or process.pid_names_executable(pid, configured, roles=roles)
    ):
        return None
    listener = process.capture_generation(pid, configured)
    if listener is None:
        return None
    return AlternateLauncher(ctx, dict(current), alternate, listener)


def _request(
    ctx: runtime_context.RuntimeContext,
    expected: dict[str, object],
    *,
    current: dict[str, object],
    listener: process.OwnedProcess,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    lease_seconds = max(1.0, timeout_seconds)
    try:
        result = handoff.request(
            ctx,
            expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            lease_seconds=lease_seconds,
            source_listener=listener,
        )
        runtime = result.get("runtime")
        if isinstance(runtime, dict):
            return runtime
        raise errors.InstallError("launcher reconciliation returned no runtime proof")
    except BaseException as error:
        resolution, runtime = handoff.resolve_after_controller_failure(
            ctx,
            current,
            expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            lease_seconds=lease_seconds,
            source_listener=listener,
        )
        if resolution == "finalized" and isinstance(runtime, dict):
            return runtime
        if resolution == "unknown":
            raise errors.InstallError(
                "launcher reconciliation outcome is unconfirmed; retry after inspecting status"
            ) from error
        raise


def _runtime_matches(
    runtime: Mapping[str, object], committed: identity.LoadedPayloadIdentity
) -> bool:
    return all(
        (
            runtime.get("release") == committed.release,
            runtime.get("serving_payload_sha256") == committed.serving_payload_sha256,
            runtime.get("release_receipt_sha256") == committed.release_receipt_sha256,
            runtime.get("payload_manifest_sha256") == committed.manifest_sha256,
            runtime.get("handoff_protocol_version") == handoff.HANDOFF_PROTOCOL_VERSION,
            runtime.get("accepting") is True,
            runtime.get("draining") is False,
        )
    )


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.realpath(os.path.abspath(left))) == os.path.normcase(
        os.path.realpath(os.path.abspath(right))
    )


def _declares_path(left: str | Path, right: str | Path) -> bool:
    """Compare the paths written into supervision without resolving launchers."""

    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _prepared_bridge(configured: str, canonical: str) -> _Bridge | None:
    """Recognize only the exact retained bridge created by this reconciler."""

    bridge = _Bridge(Path(configured), Path(canonical))
    if (
        bridge.alternate.is_symlink()
        and _same_path(bridge.alternate, bridge.canonical)
        and bridge.backup.is_file()
    ):
        return bridge
    return None


def _remove_empty_launcher_directories(directory: Path, install_root: Path) -> None:
    """Remove only now-empty launcher directories below the installed root."""

    try:
        root = install_root.resolve(strict=True)
        current = directory.resolve(strict=True)
        current.relative_to(root)
    except (OSError, ValueError):
        return
    while current != root:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
