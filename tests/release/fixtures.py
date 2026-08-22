"""Native release lifecycle fixtures shared by distribution acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import native_service
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import inventory
from tools.release import assets as release_assembly
from tools.release import product_assets
from tools.release import signing

ROOT = Path(__file__).resolve().parents[2]
COMMAND_TIMEOUT_SECONDS = 180


def _macos_service_projection() -> tuple[
    frozenset[str], frozenset[tuple[str, str]], tuple[tuple[str, str], ...]
]:
    """Return every persistent launchd surface owned by this product."""

    completed = subprocess.run(
        ["/bin/launchctl", "list"],
        capture_output=True,
        check=True,
        text=True,
    )
    labels = frozenset(
        fields[2]
        for line in completed.stdout.splitlines()[1:]
        if len(fields := line.split("\t")) >= 3 and fields[2].startswith(runtime_context.SERVICE_ID)
    )
    getuid: object = getattr(os, "getuid", None)
    if not callable(getuid):
        raise RuntimeError("macOS user identity is unavailable")
    disabled = subprocess.run(
        ["/bin/launchctl", "print-disabled", f"gui/{cast(Callable[[], int], getuid)()}"],
        capture_output=True,
        check=True,
        text=True,
    )
    overrides: frozenset[tuple[str, str]] = frozenset(
        (str(match.group("label")), str(match.group("state")))
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
    return labels, overrides, plists


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


def signed_asset(
    bundle: Path,
    output: Path,
    *,
    version: str,
    upstream_url: str,
    key: Path,
    trust: str,
) -> Path:
    """Build one route-controlled asset from exact native bundle bytes."""

    platform_id = "macos-arm64"
    executable = bundle / "codex-responses-proxy"
    files: dict[str, bytes | product_assets.ArchiveFile] = {
        "bin/codex-responses-proxy": product_assets.ArchiveFile(executable.read_bytes(), 0o755),
        "providers.toml": (
            f'version = 1\n\n[providers.dmxapi]\nbase_url = "{upstream_url}"\npolicy = "dmxapi"\n'
        ).encode(),
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

    return runtime_context.RuntimeContext(
        user_home=str(home),
        install_dir=str(install),
        executable=inventory.installed_executable(str(install)),
        command=str(home / ".local/bin/codex-responses-proxy"),
        log_dir=str(state),
        port=port,
    )


def native_environment(home: Path, install: Path, state: Path) -> dict[str, str]:
    """Return a minimal isolated environment for one native installation."""

    return {
        "CODEX_RESPONSES_PROXY_HOME": str(install),
        "CODEX_RESPONSES_PROXY_STATE_HOME": str(state),
        "HOME": str(home),
        "PATH": os.pathsep.join(("/usr/bin", "/bin", "/usr/sbin", "/sbin")),
        "PYTHONNOUSERSITE": "1",
        "USERPROFILE": str(home),
    }


def cleanup_runtime(ctx: runtime_context.RuntimeContext, wrapper: Path | None = None) -> None:
    """Stop only processes and launch configuration owned by an isolated test."""

    service = native_service.adapter()
    try:
        service.uninstall(ctx)
        assert service.status(ctx) == "absent"
    finally:
        if wrapper is not None:
            for pid in process.pids_naming_path(str(wrapper)):
                process.terminate_pid(pid, expected_path=str(wrapper))
        roles = {
            "--internal-listener",
            "--internal-handoff-child",
            "--internal-watchdog",
        }
        for pid in process.pids_naming_executable(ctx.executable, roles=roles):
            process.terminate_executable(pid, ctx.executable, roles=roles)
