"""Native release lifecycle fixtures shared by distribution acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

import psutil
import pytest

from codex_responses_proxy import errors
from codex_responses_proxy import product_identity
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import command
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle.supervision import native_service
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime.process_environment import native_process_environment
from codex_responses_proxy.service import inventory
from codex_responses_proxy.service import runtime as service_runtime
from tools.release.artifact import bundle as release_assembly
from tools.release.artifact import format as product_assets
from tools.release.artifact import signing

ROOT = Path(__file__).resolve().parents[2]
COMMAND_TIMEOUT_SECONDS = 180
_SERVICE_ROLES = frozenset(
    {
        service_runtime.LISTENER_MODE,
        service_runtime.HANDOFF_CHILD_MODE,
        service_runtime.WATCHDOG_MODE,
        service_runtime.PREWARM_MODE,
    }
)


def _macos_service_projection() -> tuple[
    frozenset[tuple[str, str]], frozenset[tuple[str, str, str]], tuple[tuple[str, str], ...]
]:
    """Return every persistent launchd surface owned by this product."""
    getuid: object = getattr(os, "getuid", None)
    if not callable(getuid):
        raise TypeError("macOS user identity is unavailable")
    uid = cast(Callable[[], int], getuid)()
    domain = f"user/{uid}"
    completed = subprocess.run(
        ["/bin/launchctl", "print", domain],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError("launchd user-domain observation failed")
    domains = [(domain, completed.stdout)]
    if re.search(r"(?m)^\tgui asid = [1-9][0-9]*\s*$", completed.stdout):
        gui = f"gui/{uid}"
        observed = subprocess.run(
            ["/bin/launchctl", "print", gui],
            capture_output=True,
            check=True,
            text=True,
        )
        domains.append((gui, observed.stdout))
    labels: set[tuple[str, str]] = set()
    overrides: set[tuple[str, str, str]] = set()
    for domain, observation in domains:
        services = re.search(r"(?ms)^\tservices = \{\n(.*?)^\t\}", observation)
        if services is None:
            raise RuntimeError("launchd domain service inventory is unproved")
        labels.update(
            (domain, fields[-1])
            for line in services.group(1).splitlines()
            if len(fields := line.split()) >= 3
            and fields[-1].startswith(runtime_context.SERVICE_ID)
        )
        disabled = subprocess.run(
            ["/bin/launchctl", "print-disabled", domain],
            capture_output=True,
            check=True,
            text=True,
        )
        overrides.update(
            (domain, str(match.group("label")), str(match.group("state")))
            for match in re.finditer(
                rf'"(?P<label>{re.escape(runtime_context.SERVICE_ID)}(?:\.[0-9a-f]{{12}})?)"'
                r"\s*=>\s*(?P<state>enabled|disabled)",
                disabled.stdout,
            )
        )
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    plists = tuple(
        (path.name, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(launch_agents.glob(f"{runtime_context.SERVICE_ID}*.plist"))
    )
    return frozenset(labels), frozenset(overrides), plists


@pytest.fixture(scope="module")
def preserve_native_host_projection():
    """Prove one native test module leaves the host projection unchanged."""
    if sys.platform != "darwin" or "CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE" not in os.environ:
        yield
        return
    before = _macos_service_projection()
    yield
    assert _macos_service_projection() == before


def run_command(
    executable: Path,
    environment: dict[str, str],
    *arguments: str,
    expected: int = 0,
) -> dict[str, object]:
    """Run one native command and require clean machine-readable output."""
    result = subprocess.run(
        [str(executable), *arguments],
        env=environment,
        text=True,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == expected, result.stderr or result.stdout
    assert "Traceback" not in result.stderr
    assert "Warning" not in result.stderr
    output = result.stdout or result.stderr
    value: object = json.loads(output)
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return {key: item for key, item in value.items() if isinstance(key, str)}


def interrupt_native_controller(
    controller: subprocess.Popen[bytes],
    executable: Path,
    identities: tuple[process.OwnedProcess, ...],
) -> None:
    """Interrupt only captured old-producer generations, children before parent."""
    ordered = sorted(identities, key=lambda owned: owned.pid == controller.pid)
    for owned in ordered:
        if not process.owned_process_alive(owned):
            continue
        try:
            native = psutil.Process(owned.pid)
            assert native.create_time() == owned.created_at
            reread = process.capture_executable(owned.pid, str(executable), roles={"install"})
            if reread is None and not process.owned_process_alive(owned):
                continue
            assert reread == owned
            native.kill()
        except psutil.NoSuchProcess:
            continue
    controller.wait(timeout=30)
    for owned in ordered:
        assert process.wait_for_exit(owned, timeout_seconds=10)
    # Inventory only after the captured producer has stopped, not in its
    # materialized-to-activated window.
    assert process.pids_naming_executable(str(executable), roles={"install"}) == []


def assert_native_target_absent(
    ctx: runtime_context.RuntimeContext,
    generations: tuple[runtime_context.RuntimeContext, ...],
) -> None:
    """Prove the public operation cleaned its target before fallback teardown."""
    service = native_service.adapter()
    assert service.status(ctx) == "absent"
    assert service.configured_executable(ctx) is None
    assert process.listener_pids(ctx.port) == []
    for owned_ctx in generations:
        assert process.pids_naming_executable(owned_ctx.executable, roles=_SERVICE_ROLES) == []
    assert not Path(ctx.command).exists()
    assert not Path(ctx.command).is_symlink()


def assert_admitted_payload_identity(
    ctx: runtime_context.RuntimeContext,
    admitted: artifact.VerifiedArtifact,
    observed: Mapping[str, object] | None = None,
) -> None:
    """Bind the complete installed payload and any live runtime to one admitted asset."""
    selected = generation.selected_context(ctx)
    root = Path(selected.payload_dir)
    assert projection.verify_payload_manifest(selected)[0]
    assert hashlib.sha256((root / inventory.RELEASE_RECEIPT_FILENAME).read_bytes()).hexdigest() == (
        admitted.receipt_sha256
    )
    expected = {blob.path for blob in admitted.peek_blobs()}
    actual = set()
    for path in root.rglob("*"):
        assert not path.is_symlink()
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    assert actual == expected | set(owned_files.OWNED_PAYLOAD_METADATA)
    for blob in admitted.peek_blobs():
        path = root.joinpath(*Path(blob.path).parts)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == blob.sha256
    if observed is not None:
        assert observed.get("state") == "running"
        assert observed.get("release") == admitted.version
        runtime = observed.get("runtime")
        assert isinstance(runtime, dict)
        assert runtime.get("release") == admitted.version
        assert runtime.get("release_receipt_sha256") == admitted.receipt_sha256
        assert runtime.get("serving_payload_sha256") == admitted.serving_payload_sha256
        assert type(runtime.get("pid")) is int
        assert runtime["pid"] > 0
        assert runtime.get("accepting") is True
        assert runtime.get("draining") is False


def signed_asset(
    bundle: Path,
    output: Path,
    *,
    version: str,
    upstream_url: str | None,
    key: Path,
    trust: str,
) -> Path:
    """Build one route-controlled asset from exact native bundle bytes."""
    platform_id = product_identity.current_native_release_platform()
    executable_name = product_identity.executable_name(windows=platform_id.startswith("windows-"))
    executable = bundle / executable_name
    files: dict[str, bytes | product_assets.ArchiveFile] = {
        f"bin/{executable_name}": product_assets.ArchiveFile(executable.read_bytes(), 0o755),
        "providers.toml": (
            (ROOT / "src/codex_responses_proxy/providers/manifest.toml").read_bytes()
            if upstream_url is None
            else (
                f'version = 1\n\n[providers.dmxapi]\nbase_url = "{upstream_url}"\npolicy = "dmxapi"\n'
            ).encode()
        ),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
    }
    for relative, source in release_assembly.bundle_files(bundle):
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


def post_response(port: int, *, stream: bool = False, timeout: float = 15) -> bytes:
    """Send one unproxied Responses request to an isolated listener."""
    body = b'{"stream": true, "input": []}' if stream else b'{"stream": false, "input": []}'
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/dmxapi/v1/responses",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        content: object = response.read()
        assert isinstance(content, bytes)
        return content


def runtime_context_for(
    home: Path, install: Path, state: Path, port: int
) -> runtime_context.RuntimeContext:
    """Return one isolated native lifecycle context."""
    environment = native_process_environment(
        user_home=home,
        install_root=install,
        state_root=state,
    )
    windows = platform.system() == "Windows"

    return runtime_context.RuntimeContext(
        user_home=str(home),
        install_dir=str(install),
        executable=inventory.installed_executable(str(install), windows=windows),
        command=str(command.path(str(home), environment, windows=windows)),
        log_dir=str(state),
        port=port,
    )


def native_service_projection(ctx: runtime_context.RuntimeContext) -> dict[str, object]:
    """Return the exact native-service and process state owned by one context."""
    service = native_service.adapter()
    return {
        "service_id": ctx.service_id,
        "status": service.status(ctx),
        "configured_executable": service.configured_executable(ctx),
        "processes": process.pids_naming_executable(ctx.executable, roles=_SERVICE_ROLES),
    }


def owned_runtime_contexts(
    ctx: runtime_context.RuntimeContext,
) -> tuple[runtime_context.RuntimeContext, ...]:
    """Return every payload context still owned by one stable installation root."""
    return generation.owned_contexts(ctx) or (ctx,)


def _process_contexts(
    ctx: runtime_context.RuntimeContext,
) -> tuple[runtime_context.RuntimeContext, ...]:
    """Include selected, unselected, and legacy executable identities for teardown."""
    contexts = (*owned_runtime_contexts(ctx), ctx)
    unique: dict[str, runtime_context.RuntimeContext] = {}
    for owned_ctx in contexts:
        unique.setdefault(owned_ctx.executable, owned_ctx)
    return tuple(unique.values())


def cleanup_runtime(ctx: runtime_context.RuntimeContext, wrapper: Path | None = None) -> None:
    """Stop only processes and launch configuration owned by an isolated test."""
    service = native_service.adapter()
    owned_contexts = _process_contexts(ctx)
    configured = service.configured_executable(ctx)
    process_contexts = owned_contexts
    if configured is not None and all(
        os.path.normcase(os.path.abspath(owned_ctx.executable))
        != os.path.normcase(os.path.abspath(configured))
        for owned_ctx in process_contexts
    ):
        configured_path = Path(configured).resolve()
        install_root = Path(ctx.install_dir).resolve()
        assert configured_path.is_relative_to(install_root), (
            "native service executable is outside the owned installation"
        )
        process_contexts = (*process_contexts, replace(ctx, executable=configured))
    failure: Exception | None = None
    try:
        service.uninstall(ctx)
        assert service.status(ctx) == "absent"
    except Exception as error:
        failure = error
    finally:
        if wrapper is not None:
            for pid in process.pids_naming_path(str(wrapper)):
                try:
                    if not process.terminate_pid(pid, expected_path=str(wrapper)):
                        raise errors.InstallError("test wrapper exit is unproved")
                except errors.InstallError as error:
                    failure = failure or error
        for owned_ctx in process_contexts:
            for pid in process.pids_naming_executable(owned_ctx.executable, roles=_SERVICE_ROLES):
                try:
                    if not process.terminate_executable(
                        pid, owned_ctx.executable, roles=_SERVICE_ROLES
                    ):
                        raise errors.InstallError("test runtime process exit is unproved")
                except errors.InstallError as error:
                    failure = failure or error
    if failure is not None:
        raise failure
    assert service.status(ctx) == "absent"
    assert service.configured_executable(ctx) is None
    assert all(
        process.pids_naming_executable(owned_ctx.executable, roles=_SERVICE_ROLES) == []
        for owned_ctx in process_contexts
    )
