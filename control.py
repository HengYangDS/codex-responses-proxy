#!/usr/bin/env python3
"""control.py — non-secret route evidence and lifecycle control for the installed proxy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from platform_adapters import pick_adapter, common  # noqa: E402


QUIESCENCE_SECONDS = 5.0
HANDOFF_PROTOCOL_VERSION = 2
_HANDOFF_MAX_BODY_BYTES = 64 * 1024


def _source_root() -> str:
    """Return the immutable source payload root for this control invocation."""
    return HERE


def _context() -> common.InstallContext:
    codex_home = common.codex_home()
    home = os.path.dirname(codex_home)
    install_dir = os.path.join(codex_home, "dmx-proxy")
    state_path = os.path.join(install_dir, common.STATE_FILENAME)
    port = common.DEFAULT_PORT
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            value = json.load(fh).get("proxy_url", "")
        if value.startswith("http://127.0.0.1:") and value.endswith("/v1"):
            port = int(value.rsplit(":", 1)[1].removesuffix("/v1"))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return common.InstallContext(
        home=home,
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "proxy", "dmx_responses_proxy.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=sys.executable,
        codex_config=os.path.join(codex_home, "config.toml"),
        log_dir=os.path.join(codex_home, "log"),
        port=port,
    )


def _aigw_config_path() -> str:
    result = subprocess.run(
        ["aigw", "config", "path"], capture_output=True, text=True, check=False,
    )
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        raise common.InstallError("could not resolve the canonical AIGW config path")
    return path


def _set_aigw_account_endpoint(account: str, endpoint: str) -> None:
    """Request an endpoint change through AIGW; never edit its config directly."""
    result = subprocess.run(
        ["aigw", "account", "edit", account, "--openai-url", endpoint],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise common.InstallError(f"AIGW endpoint update failed: {detail or 'unknown error'}")


def adopt_aigw_route(ctx: common.InstallContext, *, account: str, direct_url: str) -> dict:
    """Record an opt-in AIGW endpoint route without parsing or writing its config.

    The only control-plane mutation later performed by this mode is a call to the
    public AIGW command.  AIGW remains the writer of its canonical config and its
    multi-target Codex projections.
    """
    config_path = _aigw_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            endpoint = common.aigw_endpoint(fh.read(), account)
    except OSError as exc:
        raise common.InstallError("could not read canonical AIGW config") from exc
    direct_url = common.normalize_upstream_url(direct_url)
    proxy_url = common.proxy_base_url(ctx.port)
    if endpoint not in (direct_url, proxy_url):
        raise common.InstallError("AIGW endpoint differs from requested direct/proxy route; refusing adoption")
    state = common.make_aigw_install_state(
        ctx, aigw_config_path=config_path, account=account, direct_url=direct_url,
    )
    common.write_install_state(ctx, state)
    return state


def set_aigw_route(ctx: common.InstallContext, state: dict | None, *, enabled: bool) -> None:
    if state is None or state.get("route_mode") != "aigw_endpoint":
        raise common.InstallError("AIGW route is unmanaged; run control.py adopt-aigw first")
    status = common.aigw_route_status(ctx, state, state["aigw_config_path"])
    if status == "drifted":
        raise common.InstallError("canonical AIGW endpoint has changed outside proxy control; refusing to overwrite it")
    target = state["proxy_url"] if enabled else state["direct_url"]
    if status != ("enabled" if enabled else "disabled"):
        _set_aigw_account_endpoint(state["aigw_account"], target)
        status = common.aigw_route_status(ctx, state, state["aigw_config_path"])
        expected = "enabled" if enabled else "disabled"
        if status != expected:
            raise common.InstallError("AIGW endpoint update did not reach the expected canonical state")


def _installed_release(ctx: common.InstallContext) -> str | None:
    try:
        with open(os.path.join(ctx.install_dir, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _runtime_metrics(ctx: common.InstallContext) -> dict | None:
    """Read the proxy's secret-free health snapshot from loopback only."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/healthz",
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _drain_request(ctx: common.InstallContext, *, enabled: bool, lease_seconds: float | None = None) -> dict:
    """Set the listener's local admission latch through its loopback control API."""
    method = "POST" if enabled else "DELETE"
    headers = {"Accept": "application/json"}
    if enabled and lease_seconds is not None:
        headers["X-DMX-Drain-Lease-Seconds"] = str(max(1, int(lease_seconds)))
    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/control/drain",
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2) as response:
            if response.status != 200:
                raise common.InstallError(f"listener drain control returned HTTP {response.status}")
            payload = json.loads(response.read())
    except common.InstallError:
        raise
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        raise common.InstallError("listener drain control is unavailable") from exc
    if not isinstance(payload, dict):
        raise common.InstallError("listener drain control returned an invalid response")
    return payload


def _set_listener_drain(
    ctx: common.InstallContext,
    *,
    enabled: bool,
    lease_seconds: float | None = None,
) -> dict:
    """Require the current verified listener to acknowledge an admission change."""
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    payload = _drain_request(ctx, enabled=enabled, lease_seconds=lease_seconds)
    observed = payload.get("draining")
    if observed is not enabled:
        raise common.InstallError("listener drain control did not reach the requested state")
    return {"listener": listeners[0], "runtime": payload}


def _wait_for_quiescent_listener(
    ctx: common.InstallContext,
    timeout_seconds: float,
    *,
    quiet_seconds: float = QUIESCENCE_SECONDS,
) -> dict:
    """Wait for a stable idle window without closing Responses admission.

    This is deliberately a *preflight*, not a weak substitute for atomic drain.
    Waiting until the listener is quiet keeps normal user traffic fully serving.
    Only after the quiet window is proven do we close admission atomically; that
    reduces maintenance-visible 503s from a busy listener to the unavoidable
    final handoff race.
    """
    if timeout_seconds <= 0:
        raise common.InstallError("drain timeout must be positive")
    if quiet_seconds <= 0:
        raise common.InstallError("quiescence window must be positive")
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    deadline = time.monotonic() + timeout_seconds
    quiet_started_at: float | None = None
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) != [old_pid]:
            raise common.InstallError("verified listener changed during quiescence preflight; refusing lifecycle mutation")
        runtime = _runtime_metrics(ctx)
        active = runtime.get("active_responses") if isinstance(runtime, dict) else None
        draining = runtime.get("draining") if isinstance(runtime, dict) else None
        if draining is False and isinstance(active, int) and not isinstance(active, bool) and active == 0:
            now = time.monotonic()
            if quiet_started_at is None:
                quiet_started_at = now
            elif now - quiet_started_at >= quiet_seconds:
                return {"listener": old_pid, "runtime": runtime}
        else:
            quiet_started_at = None
        time.sleep(0.1)
    raise common.InstallError(
        f"listener did not remain quiescent for {quiet_seconds:g}s within {timeout_seconds:g}s; "
        "no drain was started"
    )


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_bytes(path: str, value: bytes) -> None:
    temporary = f"{path}.tmp-{os.getpid()}"
    try:
        with open(temporary, "wb") as fh:
            fh.write(value)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass


def _verified_source_revision() -> str:
    """Require a clean, committed source worktree for a live controller apply."""
    source = _source_root()
    inside = subprocess.run(
        ["git", "-C", source, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise common.InstallError("controller-only apply requires a Git source worktree")
    state = subprocess.run(
        ["git", "-C", source, "status", "--porcelain=v1"],
        capture_output=True,
        text=True,
        check=False,
    )
    if state.returncode != 0:
        raise common.InstallError("could not verify source worktree cleanliness")
    if state.stdout.strip():
        raise common.InstallError("controller-only apply requires a clean source worktree")
    revision = subprocess.run(
        ["git", "-C", source, "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = revision.stdout.strip()
    if revision.returncode != 0 or len(value) != 40:
        raise common.InstallError("could not resolve source revision for controller-only apply")
    return value


def _validate_control_plane_source(ctx: common.InstallContext) -> bool:
    """Prove this source changes only the installed lifecycle controller.

    ``apply-control-plane`` is not a partial payload upgrade.  Every declared
    listener, watchdog, version, and support file must exactly match the verified
    live payload.  Only ``control.py`` may differ; otherwise the caller must use
    the ordinary staged upgrade path.
    """
    source = os.path.abspath(_source_root())
    live = os.path.abspath(ctx.install_dir)
    if source == live:
        return False
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"live payload integrity check failed: {integrity_detail}")
    missing = [
        relative
        for relative in common.RUNTIME_PAYLOAD_FILES
        if not os.path.isfile(os.path.join(source, relative))
    ]
    if missing:
        raise common.InstallError("source payload is incomplete: " + ", ".join(missing))
    changed = [
        relative
        for relative in common.RUNTIME_PAYLOAD_FILES
        if relative != "control.py"
        and _sha256_file(os.path.join(source, relative))
        != _sha256_file(os.path.join(ctx.install_dir, relative))
    ]
    if changed:
        raise common.InstallError(
            "source payload changes outside the lifecycle control plane; use a staged upgrade: "
            + ", ".join(changed)
        )
    return (
        _sha256_file(os.path.join(source, "control.py"))
        != _sha256_file(os.path.join(ctx.install_dir, "control.py"))
    )


def _commit_current_control_plane(ctx: common.InstallContext) -> bool:
    """Transactionally install a verified controller-only source change.

    The proxy listener does not import this controller while serving a request.
    The operation writes one controller file, updates its manifest, and restores
    the exact prior controller and manifest if either verification fails.
    """
    if not _validate_control_plane_source(ctx):
        return False
    source_control = os.path.join(_source_root(), "control.py")
    live_control = os.path.join(ctx.install_dir, "control.py")
    manifest_path = common.payload_manifest_path(ctx)
    previous_control = Path(live_control).read_bytes()
    previous_manifest = Path(manifest_path).read_bytes()
    temporary = f"{live_control}.next-{os.getpid()}"
    try:
        shutil.copy2(source_control, temporary)
        if _sha256_file(temporary) != _sha256_file(source_control):
            raise common.InstallError("source controller digest changed during apply")
        os.replace(temporary, live_control)
        common.write_payload_manifest(ctx)
        integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
        if not integrity_ok:
            raise common.InstallError(
                f"controller-only manifest verification failed: {integrity_detail}"
            )
    except Exception as exc:
        _atomic_write_bytes(live_control, previous_control)
        _atomic_write_bytes(manifest_path, previous_manifest)
        restored, restored_detail = common.verify_payload_manifest(ctx)
        if not restored:
            raise common.InstallError(
                f"controller-only apply failed and restoration verification failed: {restored_detail}"
            ) from exc
        raise
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
    return True


def _drain_listener(ctx: common.InstallContext, timeout_seconds: float) -> dict:
    """Quiesce first, then close admission and prove the same listener drained.

    The listener owns the latch and counter under one lock.  Thus an acknowledged
    snapshot with ``draining=true`` and ``active_responses=0`` proves that no new
    Responses request can enter before the listener is terminated.
    """
    quiescent = _wait_for_quiescent_listener(ctx, timeout_seconds)
    old_pid = quiescent["listener"]
    baseline = _set_listener_drain(ctx, enabled=True, lease_seconds=timeout_seconds + 5)
    if baseline["listener"] != old_pid:
        try:
            _set_listener_drain(ctx, enabled=False)
        except common.InstallError:
            pass
        raise common.InstallError("verified listener changed while admission was closing; service restored to admission")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        listeners = common.verified_proxy_listener_pids(ctx)
        if listeners != [old_pid]:
            raise common.InstallError("verified listener changed during drain; refusing lifecycle mutation")
        runtime = _runtime_metrics(ctx)
        if not isinstance(runtime, dict):
            time.sleep(0.1)
            continue
        active = runtime.get("active_responses")
        if runtime.get("draining") is True and isinstance(active, int) and not isinstance(active, bool) and active == 0:
            return {"listener": old_pid, "runtime": runtime}
        time.sleep(0.1)
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"listener did not drain active Responses within {timeout_seconds:g}s; service restored to admission"
    )


def _legacy_drain_listener(
    ctx: common.InstallContext,
    timeout_seconds: float,
    *,
    required_idle_seconds: float = 1.0,
) -> dict:
    """Quiesce a pre-drain listener with two consecutive zero snapshots.

    This compatibility path is intentionally narrower than the current atomic
    drain protocol.  It exists only to replace an older installed listener that
    predates ``/control/drain``.  Two zero samples separated by a short quiet
    interval reduce the handoff window; the new 1.0.22 listener then supplies
    the durable atomic admission barrier for every subsequent lifecycle action.
    """
    if timeout_seconds <= 0:
        raise common.InstallError("drain timeout must be positive")
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    deadline = time.monotonic() + timeout_seconds
    if required_idle_seconds <= 0:
        raise common.InstallError("legacy idle window must be positive")
    previous_zero_at: float | None = None
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) != [old_pid]:
            raise common.InstallError("verified listener changed during legacy drain; refusing lifecycle mutation")
        runtime = _runtime_metrics(ctx)
        active = runtime.get("active_responses") if isinstance(runtime, dict) else None
        if isinstance(active, int) and not isinstance(active, bool) and active == 0:
            now = time.monotonic()
            if previous_zero_at is not None and now - previous_zero_at >= required_idle_seconds:
                return {"listener": old_pid, "runtime": runtime, "legacy": True}
            previous_zero_at = now
        else:
            previous_zero_at = None
        time.sleep(0.1)
    raise common.InstallError(
        f"legacy listener did not remain idle for {required_idle_seconds:g}s within {timeout_seconds:g}s; "
        "payload was not changed"
    )


def _drain_listener_with_legacy_bootstrap(
    ctx: common.InstallContext,
    timeout_seconds: float,
    *,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
) -> dict:
    """Use atomic drain when available; bootstrap exactly one legacy listener otherwise."""
    try:
        return _drain_listener(ctx, timeout_seconds)
    except common.InstallError as exc:
        if str(exc) != "listener drain control is unavailable":
            raise
    if not allow_legacy_bootstrap:
        raise common.InstallError(
            "listener predates atomic drain control; retry after an operator-approved maintenance window"
        )
    if force_legacy_bootstrap:
        integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
        if not integrity_ok:
            raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
        listeners = common.verified_proxy_listener_pids(ctx)
        if len(listeners) != 1:
            raise common.InstallError(
                f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
            )
        return {"listener": listeners[0], "legacy": True, "forced": True}
    return _legacy_drain_listener(ctx, timeout_seconds, required_idle_seconds=5.0)


def _runtime_supports_handoff(runtime: dict | None) -> bool:
    """Report whether a live listener's own health snapshot advertises protocol-v2 handoff.

    A legacy runtime -- ``None``, an empty dict, or any snapshot that predates
    the ``handoff_protocol_version`` key entirely (an installed 1.0.24, for
    instance) -- is reported as unsupported so callers fall back to the
    existing drain/terminate/watchdog path unchanged.
    """
    if not isinstance(runtime, dict):
        return False
    pid = runtime.get("pid")
    source = runtime.get("source_sha256")
    manifest = runtime.get("payload_manifest_sha256")
    release = runtime.get("release")
    handoff_state = runtime.get("handoff_state")
    transaction_id = runtime.get("handoff_transaction_id")
    transaction_state_ok = (
        (handoff_state == "idle" and transaction_id is None)
        or (
            handoff_state == "finalized"
            and isinstance(transaction_id, str)
            and bool(transaction_id)
        )
    )
    return (
        runtime.get("handoff_protocol_version") == HANDOFF_PROTOCOL_VERSION
        and isinstance(pid, int)
        and not isinstance(pid, bool)
        and pid > 0
        and isinstance(release, str)
        and bool(release)
        and _valid_sha256(source)
        and _valid_sha256(manifest)
        and runtime.get("accepting") is True
        and runtime.get("draining") is False
        and transaction_state_ok
    )


def _valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _expected_handoff_metadata(root: str) -> dict:
    """Compute the release/source/manifest identity a handoff child must prove.

    ``root`` is either the live installed payload (``ctx.install_dir`` for
    ``reload()``) or an already-verified staged payload (for
    ``upgrade_from_stage()``); this never trusts caller-supplied text for the
    expected identity, only bytes read directly from that verified payload.
    """
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
            release = fh.read().strip()
    except OSError as exc:
        raise common.InstallError(f"payload VERSION is unavailable: {exc}") from exc
    if not release:
        raise common.InstallError("payload has no release version")
    try:
        source_sha256 = _sha256_file(os.path.join(root, "proxy", "dmx_responses_proxy.py"))
        manifest_sha256 = _sha256_file(os.path.join(root, common.PAYLOAD_MANIFEST_FILENAME))
    except OSError as exc:
        raise common.InstallError(f"payload files are unavailable for a handoff transaction: {exc}") from exc
    return {
        "transaction_id": uuid.uuid4().hex,
        "release": release,
        "source_sha256": source_sha256,
        "manifest_sha256": manifest_sha256,
    }


def _handoff_post(
    ctx: common.InstallContext,
    expected: dict,
    *,
    lease_seconds: float | None = None,
    timeout_seconds: float = 5.0,
) -> dict:
    """POST the loopback-only handoff control endpoint and require an HTTP 202 ready ack."""
    body = {
        "transaction_id": expected["transaction_id"],
        "release": expected["release"],
        "source_sha256": expected["source_sha256"],
        "manifest_sha256": expected["manifest_sha256"],
    }
    if lease_seconds is not None:
        body["lease_seconds"] = max(1, int(lease_seconds))
    body["timeout_seconds"] = max(1, min(120, int(timeout_seconds)))
    data = json.dumps(body).encode("utf-8")
    if len(data) > _HANDOFF_MAX_BODY_BYTES:
        raise common.InstallError("handoff request payload is too large")
    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/control/handoff",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            if response.status != 202:
                raise common.InstallError(f"handoff control returned HTTP {response.status}")
            raw = response.read(_HANDOFF_MAX_BODY_BYTES + 1)
            if len(raw) > _HANDOFF_MAX_BODY_BYTES:
                raise common.InstallError("handoff control response is too large")
            payload = json.loads(raw)
    except common.InstallError:
        raise
    except urllib.error.HTTPError as exc:
        raise common.InstallError(f"handoff control returned HTTP {exc.code}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        raise common.InstallError("handoff control is unavailable") from exc
    if not isinstance(payload, dict):
        raise common.InstallError("handoff control returned an invalid response")
    if (
        payload.get("ok") is not True
        or payload.get("state") != "ready"
        or payload.get("protocol_version") != HANDOFF_PROTOCOL_VERSION
    ):
        raise common.InstallError("handoff control did not return a protocol-v2 READY acknowledgement")
    if payload.get("transaction_id") != expected["transaction_id"]:
        raise common.InstallError("handoff control acknowledged an unexpected transaction")
    child_pid = payload.get("child_pid")
    if not isinstance(child_pid, int) or isinstance(child_pid, bool) or child_pid <= 0:
        raise common.InstallError("handoff control response is missing a valid child pid")
    return payload


def _handoff_runtime_matches(runtime: dict | None, expected: dict, child_pid: int) -> bool:
    """Require the new listener's own health snapshot to prove it is exactly the expected child."""
    if not isinstance(runtime, dict):
        return False
    if runtime.get("pid") != child_pid:
        return False
    if runtime.get("handoff_protocol_version") != HANDOFF_PROTOCOL_VERSION:
        return False
    if runtime.get("handoff_transaction_id") != expected["transaction_id"]:
        return False
    if runtime.get("release") != expected["release"]:
        return False
    if runtime.get("source_sha256") != expected["source_sha256"]:
        return False
    if runtime.get("payload_manifest_sha256") != expected["manifest_sha256"]:
        return False
    if runtime.get("accepting") is not True:
        return False
    if runtime.get("draining") is not False:
        return False
    if runtime.get("handoff_state") not in {"serving", "finalized"}:
        return False
    return True


def _request_handoff(
    ctx: common.InstallContext,
    expected: dict,
    *,
    timeout_seconds: float = 30.0,
    lease_seconds: float = 30.0,
) -> dict:
    """Ask the current verified listener to hand off to a new child; never terminate anything.

    Requires exactly one verified old listener before posting.  A transient
    dual-accept window (the old and new listener both verified at once) is not
    treated as success; only an *exact* ``[child_pid]`` verified-listener set,
    together with the child's own health snapshot proving every expected
    release/source/manifest/transaction field and ``accepting is True``, counts
    as proof.  Never calls ``common.terminate_pid`` on any PID.
    """
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    ready = _handoff_post(ctx, expected, lease_seconds=lease_seconds, timeout_seconds=min(timeout_seconds, 10.0))
    child_pid = ready["child_pid"]
    convergence_seconds = timeout_seconds * 3 + max(1.0, lease_seconds) + 5.0
    deadline = time.monotonic() + convergence_seconds
    while time.monotonic() < deadline:
        current_listeners = common.verified_proxy_listener_pids(ctx)
        if current_listeners == [child_pid]:
            runtime = _runtime_metrics(ctx)
            if _handoff_runtime_matches(runtime, expected, child_pid):
                return {
                    "old_pid": old_pid,
                    "new_pid": child_pid,
                    "child_pid": child_pid,
                    "transaction_id": expected["transaction_id"],
                    "release": expected["release"],
                    "runtime": runtime,
                }
            raise common.InstallError(
                f"handoff child {child_pid} health snapshot did not match the expected transaction"
            )
        time.sleep(0.1)
    raise common.InstallError(
        f"handoff did not converge on verified listener {child_pid} within {convergence_seconds:g}s"
    )


def _wait_for_handoff_rollback(
    ctx: common.InstallContext,
    old_runtime: dict,
    *,
    timeout_seconds: float,
) -> dict:
    """Confirm the exact old process resumed normal admission after ABORT."""
    old_pid = old_runtime["pid"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) == [old_pid]:
            runtime = _runtime_metrics(ctx)
            if (
                isinstance(runtime, dict)
                and runtime.get("pid") == old_pid
                and runtime.get("source_sha256") == old_runtime.get("source_sha256")
                and runtime.get("payload_manifest_sha256") == old_runtime.get("payload_manifest_sha256")
                and runtime.get("handoff_protocol_version") == HANDOFF_PROTOCOL_VERSION
                and runtime.get("handoff_state") == "idle"
                and runtime.get("handoff_transaction_id") is None
                and runtime.get("accepting") is True
                and runtime.get("draining") is False
            ):
                return runtime
        time.sleep(0.1)
    raise common.InstallError(
        f"old proxy listener {old_pid} did not resume after handoff rollback within {timeout_seconds:g}s"
    )


def _resolve_handoff_after_controller_failure(
    ctx: common.InstallContext,
    old_runtime: dict,
    expected: dict,
    *,
    timeout_seconds: float,
    lease_seconds: float,
) -> tuple[str, dict | None]:
    """Resolve a controller-side failure without racing an autonomous FINALIZE."""
    old_pid = old_runtime["pid"]
    deadline = time.monotonic() + timeout_seconds + max(1.0, lease_seconds) + 5.0
    while time.monotonic() < deadline:
        listeners = common.verified_proxy_listener_pids(ctx)
        runtime = _runtime_metrics(ctx)
        if isinstance(runtime, dict):
            pid = runtime.get("pid")
            if (
                isinstance(pid, int)
                and pid != old_pid
                and listeners == [pid]
                and _handoff_runtime_matches(runtime, expected, pid)
            ):
                return "finalized", runtime
            if (
                listeners == [old_pid]
                and runtime.get("pid") == old_pid
                and runtime.get("source_sha256") == old_runtime.get("source_sha256")
                and runtime.get("handoff_protocol_version") == HANDOFF_PROTOCOL_VERSION
                and runtime.get("handoff_state") == "idle"
                and runtime.get("handoff_transaction_id") is None
                and runtime.get("accepting") is True
                and runtime.get("draining") is False
            ):
                return "rolled_back", runtime
        time.sleep(0.1)
    return "unknown", None


def status(ctx: common.InstallContext) -> dict:
    """Return non-secret runtime evidence for the installed projection."""
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    listeners = common.verified_proxy_listener_pids(ctx)
    try:
        service = pick_adapter().status(ctx)
    except Exception:
        service = "unknown"
    state = common.load_install_state(ctx)
    return {
        "release": _installed_release(ctx),
        "payload_integrity": {"ok": integrity_ok, "detail": integrity_detail},
        "route_authority": common.route_authority(ctx),
        "route_mode": state.get("route_mode") if state else None,
        "route": common.route_status(ctx, state),
        "service": service,
        "listener_pids": listeners,
        "runtime": _runtime_metrics(ctx),
    }


def reload(
    ctx: common.InstallContext,
    timeout_seconds: float = 30.0,
) -> dict[str, int]:
    """Replace exactly one verified listener; prefer a live handoff over drain+restart.

    A listener whose own health snapshot advertises protocol-v2 handoff support
    is asked to prepare and hand off to a new child on its own already-open
    listening socket; the old listener is never terminated by this controller
    and keeps serving until the new one proves it.  A listener that predates
    handoff keeps the existing drain -> terminate -> watchdog-replace path
    unchanged.
    """
    runtime = _runtime_metrics(ctx)
    if _runtime_supports_handoff(runtime):
        integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
        if not integrity_ok:
            raise common.InstallError(
                f"payload integrity check failed before handoff reload: {integrity_detail}"
            )
        expected = _expected_handoff_metadata(ctx.install_dir)
        lease_seconds = max(1.0, timeout_seconds)
        try:
            result = _request_handoff(
                ctx,
                expected,
                timeout_seconds=timeout_seconds,
                lease_seconds=lease_seconds,
            )
        except BaseException as handoff_exc:
            try:
                resolution, resolved_runtime = _resolve_handoff_after_controller_failure(
                    ctx,
                    runtime,
                    expected,
                    timeout_seconds=timeout_seconds,
                    lease_seconds=lease_seconds,
                )
            except BaseException:
                resolution, resolved_runtime = "unknown", None
            if resolution == "finalized" and isinstance(resolved_runtime, dict):
                return {
                    "old_pid": runtime["pid"],
                    "new_pid": resolved_runtime["pid"],
                    "transaction_id": expected["transaction_id"],
                    "recovered_after_controller_failure": True,
                }
            if resolution == "unknown":
                raise common.InstallError(
                    "reload handoff outcome is unconfirmed; inspect the transaction-bound listener health"
                ) from handoff_exc
            raise
        return {"old_pid": result["old_pid"], "new_pid": result["child_pid"]}
    old_pid = _drain_listener_with_legacy_bootstrap(ctx, timeout_seconds)["listener"]
    try:
        common.terminate_pid(old_pid)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for pid in common.verified_proxy_listener_pids(ctx):
                if pid != old_pid:
                    return {"old_pid": old_pid, "new_pid": pid}
            time.sleep(0.1)
    except Exception:
        try:
            _set_listener_drain(ctx, enabled=False)
        except common.InstallError:
            pass
        raise
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"watchdog did not replace verified proxy listener {old_pid} within {timeout_seconds:g}s; "
        "service restored to admission"
    )


def apply_control_plane(ctx: common.InstallContext) -> dict[str, object]:
    """Apply a verified controller-only fix without touching Responses admission.

    The listener and watchdog never import ``control.py`` while serving traffic.
    After proving their entire payload is byte-identical to the candidate source,
    this transaction may update only the lifecycle controller and manifest. It
    therefore does not drain, terminate, restart, or otherwise interrupt an
    active Responses stream.
    """
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    runtime = _runtime_metrics(ctx)
    if not isinstance(runtime, dict) or runtime.get("draining") is not False:
        raise common.InstallError(
            "verified listener is not serving normal admission; refusing controller-only apply"
        )
    source_revision = _verified_source_revision()
    changed = _commit_current_control_plane(ctx)
    current_runtime = _runtime_metrics(ctx)
    if common.verified_proxy_listener_pids(ctx) != listeners:
        raise common.InstallError("verified listener changed during controller-only apply")
    if not isinstance(current_runtime, dict) or current_runtime.get("draining") is not False:
        raise common.InstallError("listener admission changed during controller-only apply")
    return {
        "listener": listeners[0],
        "release": _installed_release(ctx),
        "draining": False,
        "changed": changed,
        "control_sha256": _sha256_file(os.path.join(ctx.install_dir, "control.py")),
        "source_revision": source_revision,
    }


def upgrade_from_stage(
    ctx: common.InstallContext,
    stage: str,
    timeout_seconds: float = 30.0,
    *,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
) -> dict[str, int | str]:
    """Commit a pre-verified stage, then replace the verified listener.

    A listener that advertises protocol-v2 handoff support is asked, before
    the staged payload is committed, whether it can hand off to a live child
    instead of being drained and replaced by a watchdog-started process; the
    old listener is never terminated by this controller and any pre-finalize
    failure (including an interrupted controller) restores and finalizes the
    payload transaction before the failure is re-raised.  A listener that
    predates handoff keeps the existing drain -> commit -> terminate ->
    watchdog-replace path unchanged, which is what carries an installed
    1.0.24 across its very first 1.0.25 migration.
    """
    staged_version = Path(stage, "VERSION").read_text(encoding="utf-8").strip()
    if not staged_version:
        raise common.InstallError("staged payload has no release version")
    rollback_dir = os.path.join(common.payload_transaction_dir(ctx), "rollback")
    if os.path.lexists(rollback_dir):
        raise common.InstallError(
            "a preserved payload rollback transaction already exists; refusing to reuse it for a new upgrade"
        )
    runtime = _runtime_metrics(ctx)
    if _runtime_supports_handoff(runtime):
        expected = _expected_handoff_metadata(stage)
        lease_seconds = max(1.0, timeout_seconds)
        handoff_invoked = False
        try:
            common.commit_payload_transaction(ctx, stage)
            handoff_invoked = True
            result = _request_handoff(
                ctx,
                expected,
                timeout_seconds=timeout_seconds,
                lease_seconds=lease_seconds,
            )
            common.finalize_payload_transaction(ctx)
            return {
                "old_pid": result["old_pid"],
                "new_pid": result["child_pid"],
                "release": expected["release"],
                "transaction_id": expected["transaction_id"],
            }
        except BaseException as handoff_exc:
            if handoff_invoked:
                try:
                    resolution, resolved_runtime = _resolve_handoff_after_controller_failure(
                        ctx,
                        runtime,
                        expected,
                        timeout_seconds=timeout_seconds,
                        lease_seconds=lease_seconds,
                    )
                except BaseException:
                    resolution, resolved_runtime = "unknown", None
                if resolution == "finalized" and isinstance(resolved_runtime, dict):
                    try:
                        common.finalize_payload_transaction(ctx)
                    except BaseException as finalize_exc:
                        raise common.InstallError(
                            f"upgrade handoff finalized but payload transaction cleanup failed: {finalize_exc}"
                        ) from handoff_exc
                    return {
                        "old_pid": runtime["pid"],
                        "new_pid": resolved_runtime["pid"],
                        "release": expected["release"],
                        "transaction_id": expected["transaction_id"],
                        "recovered_after_controller_failure": True,
                    }
                if resolution == "unknown":
                    raise common.InstallError(
                        "upgrade handoff outcome is unconfirmed; payload transaction was preserved for recovery"
                    ) from handoff_exc
            if not os.path.isdir(rollback_dir):
                raise
            try:
                common.restore_payload_transaction(ctx)
            except BaseException as rollback_exc:
                raise common.InstallError(
                    f"upgrade handoff failed and payload rollback failed: {rollback_exc}"
                ) from handoff_exc
            try:
                _wait_for_handoff_rollback(
                    ctx,
                    runtime,
                    timeout_seconds=timeout_seconds,
                )
            except BaseException as resume_exc:
                raise common.InstallError(
                    f"upgrade handoff failed, payload restored, but old listener did not resume: {resume_exc}"
                ) from handoff_exc
            try:
                common.finalize_payload_transaction(ctx)
            except BaseException as finalize_exc:
                raise common.InstallError(
                    f"upgrade handoff failed and rollback transaction finalization failed: {finalize_exc}"
                ) from handoff_exc
            raise
    old_pid = _drain_listener_with_legacy_bootstrap(
        ctx,
        timeout_seconds,
        allow_legacy_bootstrap=allow_legacy_bootstrap,
        force_legacy_bootstrap=force_legacy_bootstrap,
    )["listener"]
    try:
        common.commit_payload_transaction(ctx, stage)
        common.terminate_pid(old_pid)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            listeners = common.verified_proxy_listener_pids(ctx)
            for pid in listeners:
                if pid == old_pid:
                    continue
                runtime = _runtime_metrics(ctx)
                if isinstance(runtime, dict) and runtime.get("release") == staged_version:
                    common.finalize_payload_transaction(ctx)
                    return {"old_pid": old_pid, "new_pid": pid, "release": staged_version}
            time.sleep(0.1)
    except Exception as exc:
        try:
            transaction = common.payload_transaction_dir(ctx)
            if os.path.isdir(os.path.join(transaction, "rollback")):
                common.restore_payload_transaction(ctx)
        except Exception as rollback_exc:
            raise common.InstallError(
                f"upgrade replacement failed and payload rollback failed: {rollback_exc}"
            ) from exc
        common.finalize_payload_transaction(ctx)
        try:
            _set_listener_drain(ctx, enabled=False)
        except common.InstallError:
            pass
        raise common.InstallError(f"upgrade replacement failed; payload restored: {exc}") from exc
    try:
        common.restore_payload_transaction(ctx)
    except Exception as rollback_exc:
        raise common.InstallError(
            f"watchdog replacement timed out and payload rollback failed: {rollback_exc}"
        ) from rollback_exc
    common.finalize_payload_transaction(ctx)
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"watchdog did not replace verified proxy listener {old_pid} with release {staged_version} "
        f"within {timeout_seconds:g}s; payload restored"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the installed Codex DMX Proxy.")
    parser.add_argument("command", choices=("status", "enable", "disable", "reload", "adopt-aigw", "apply-control-plane", "upgrade"))
    parser.add_argument("--stage", help="validated payload stage created by install.py --stage-only")
    parser.add_argument("--aigw-account", default="dmx", help="AIGW account ID for adopt-aigw")
    parser.add_argument("--direct-url", default=common.DEFAULT_UPSTREAM + "/v1", help="direct Responses endpoint for adopt-aigw")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--allow-legacy-bootstrap",
        action="store_true",
        help="allow the one-time pre-drain listener upgrade after its five-second quiet window",
    )
    parser.add_argument(
        "--force-legacy-bootstrap",
        action="store_true",
        help="interrupt active Responses only for an explicitly authorized one-time pre-drain listener upgrade",
    )
    args = parser.parse_args()
    ctx = _context()
    state = common.load_install_state(ctx)

    if args.command == "adopt-aigw":
        try:
            state = adopt_aigw_route(ctx, account=args.aigw_account, direct_url=args.direct_url)
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        evidence = {"route": common.aigw_route_status(ctx, state, state["aigw_config_path"]), "authority": "aigw"}
        print(json.dumps(evidence, sort_keys=True) if args.as_json else "route: " + evidence["route"] + "\nauthority: AIGW canonical endpoint")
        return

    if args.command == "status":
        evidence = status(ctx)
        if args.as_json:
            print(json.dumps(evidence, sort_keys=True))
        else:
            print(f"release: {evidence['release'] or 'unavailable'}")
            print(f"payload integrity: {'ok' if evidence['payload_integrity']['ok'] else 'FAILED'} ({evidence['payload_integrity']['detail']})")
            print(f"route authority: {evidence['route_authority']}")
            print(f"route: {evidence['route']}")
            print(f"service: {evidence['service']}")
            print(f"verified listener pids: {', '.join(map(str, evidence['listener_pids'])) or 'none'}")
            runtime = evidence["runtime"]
            if runtime is None:
                print("runtime metrics: unavailable")
            else:
                print(f"runtime metrics: {runtime['uptime_seconds']}s uptime; "
                      f"{runtime['active_responses']} active Responses request(s)")
        return

    if args.command == "reload":
        try:
            evidence = reload(
                ctx,
                timeout_seconds=args.timeout_seconds,
            )
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(json.dumps(evidence, sort_keys=True) if args.as_json else f"reloaded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']}")
        return

    if args.command == "apply-control-plane":
        try:
            evidence = apply_control_plane(ctx)
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(json.dumps(evidence, sort_keys=True) if args.as_json else (
            f"applied lifecycle control to verified proxy listener {evidence['listener']}"
        ))
        return

    if args.command == "upgrade":
        if not args.stage:
            raise SystemExit("ERROR: upgrade requires --stage")
        if args.force_legacy_bootstrap and not args.allow_legacy_bootstrap:
            raise SystemExit("ERROR: --force-legacy-bootstrap requires --allow-legacy-bootstrap")
        try:
            evidence = upgrade_from_stage(
                ctx,
                args.stage,
                timeout_seconds=args.timeout_seconds,
                allow_legacy_bootstrap=args.allow_legacy_bootstrap,
                force_legacy_bootstrap=args.force_legacy_bootstrap,
            )
        except (common.InstallError, OSError) as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(json.dumps(evidence, sort_keys=True) if args.as_json else (
            f"upgraded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']} "
            f"(release {evidence['release']})"
        ))
        return

    try:
        if state is not None and state.get("route_mode") == "aigw_endpoint":
            set_aigw_route(ctx, state, enabled=args.command == "enable")
        elif common.route_authority(ctx) == "aigw":
            raise common.InstallError("AIGW owns the route; use AIGW or explicitly adopt-aigw first")
        else:
            common.set_proxy_route(ctx, state, enabled=args.command == "enable")
    except common.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"route: {args.command}d")
    print("Reload Codex through its normal client lifecycle before expecting an already-running client to use a changed route.")


if __name__ == "__main__":
    main()
