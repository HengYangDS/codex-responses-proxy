"""Construction helpers for released-payload lifecycle tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath

from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import transaction as payload_transaction
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import inventory

ROOT = Path(__file__).resolve().parents[2]


def install_context(root: Path, *, windows: bool = False) -> runtime_context.RuntimeContext:
    """Build an isolated install context for one explicitly modeled platform."""

    install_dir = root / "data" / "codex-responses-proxy"
    executable = inventory.installed_executable(str(install_dir), windows=windows)
    return runtime_context.RuntimeContext(
        home=str(root),
        install_dir=str(install_dir),
        executable=executable,
        log_dir=str(root / "state" / "codex-responses-proxy"),
        port=8791,
    )


def platform_context(port: int = 8791, *, windows: bool = False) -> runtime_context.RuntimeContext:
    """Build a deterministic service-definition fixture for one modeled platform."""

    if windows:
        home = PureWindowsPath("C:/fixture-home")
        install_dir = home / "AppData" / "Local" / "codex-responses-proxy"
        log_dir = home / "AppData" / "Local" / "codex-responses-proxy" / "state"
    else:
        home = PurePosixPath("/fixture-home")
        install_dir = home / ".local" / "share" / "codex-responses-proxy"
        log_dir = home / ".local" / "state" / "codex-responses-proxy"
    return runtime_context.RuntimeContext(
        home=str(home),
        install_dir=str(install_dir),
        executable=inventory.installed_executable(str(install_dir), windows=windows),
        log_dir=str(log_dir),
        port=port,
    )


def runtime_files(*, windows: bool = False) -> tuple[str, str]:
    """Return the installed payload inventory for the modeled platform."""

    return inventory.runtime_files(windows=windows)


def executable_relative(*, windows: bool = False) -> str:
    """Return the installed executable member for the modeled platform."""

    return inventory.executable_name(windows=windows)


def assert_private_log_mode(testcase, mode: int) -> None:
    """Assert the strongest portable privacy bits exposed by the host."""

    if os.name == "nt":
        assert mode & 384 == 384
    else:
        assert mode == 384


def released_artifact(version: str = "1.2.3") -> artifact.VerifiedArtifact:
    """Build an admitted release artifact for lifecycle behavior tests."""

    def blob(relative: str) -> artifact.ArtifactFile:
        content = (
            b"native-executable-fixture"
            if relative in {inventory.EXECUTABLE, inventory.WINDOWS_EXECUTABLE}
            else (ROOT / "src/codex_responses_proxy/providers/manifest.toml").read_bytes()
        )
        return artifact.ArtifactFile(
            path=relative,
            mode="100755" if relative != inventory.PROVIDER_MANIFEST else "100644",
            blob_oid=hashlib.sha1(content).hexdigest(),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )

    files = runtime_files()
    blobs = tuple(map(blob, files))
    serving = {item.path: item.sha256 for item in blobs if item.path in files}
    receipt = {
        "schema_version": 1,
        "version": version,
        "serving_payload_sha256": projection.serving_payload_sha256(serving),
        "serving_files": list(files),
        "payload": [
            dict(path=item.path, mode=item.mode, blob_oid=item.blob_oid, sha256=item.sha256)
            for item in blobs
        ],
    }
    receipt_sha256 = hashlib.sha256(payload_digest.canonical_json(receipt)).hexdigest()
    return artifact.mint(
        blobs,
        receipt,
        {
            "schema_version": 1,
            "algorithm": "sha256",
            "receipt_sha256": receipt_sha256,
            "serving_payload_sha256": receipt["serving_payload_sha256"],
        },
    )


def begin_transaction(
    ctx: runtime_context.RuntimeContext, candidate: artifact.VerifiedArtifact, *, mocker
) -> payload_transaction.PayloadTransaction:
    """Begin a transaction through the artifact claim authority boundary."""

    if not isinstance(candidate, artifact.VerifiedArtifact):
        return payload_transaction.begin_transaction(ctx, candidate)
    blobs = candidate.peek_blobs()
    receipt = candidate.receipt
    claimed = (blobs, candidate.version, candidate.receipt_sha256, receipt, {})
    mocker.patch.object(artifact, "claim", return_value=claimed)
    return payload_transaction.begin_transaction(ctx, candidate)


def install_payload(
    ctx: runtime_context.RuntimeContext, version: str = "1.2.3", *, mocker
) -> payload_transaction.PayloadTransaction:
    """Install and finalize one released payload projection."""

    transaction = begin_transaction(ctx, released_artifact(version), mocker=mocker)
    transaction.commit_projection()
    transaction.finalize({"pid": 1})
    return transaction


def write_retired_projection(
    ctx: runtime_context.RuntimeContext,
    *,
    version: str = "1.0.27",
    schema: int = 2,
    overrides: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    """Write one exact historical manifest inventory for lifecycle tests."""

    files = {
        relative: (f"{version}\n".encode() if relative == "VERSION" else f"{relative}\n".encode())
        for relative in projection._RETIRED_RUNTIME_FILES[schema]
    }
    files.update(overrides or {})
    if set(files) != set(projection._RETIRED_RUNTIME_FILES[schema]):
        raise AssertionError("retired fixture must match one exact historical inventory")
    install = Path(ctx.install_dir)
    for relative, content in files.items():
        target = install / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {
        "schema_version": schema,
        "release": version,
        "files": {
            relative: hashlib.sha256(content).hexdigest() for relative, content in files.items()
        },
    }
    (install / inventory.MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return files


def write_direct_predecessor_projection(
    ctx: runtime_context.RuntimeContext,
) -> dict[str, bytes]:
    """Write the exact installed projection accepted for direct upgrade."""

    version = "2.0.10"
    files, serving_paths = projection._DIRECT_PREDECESSOR_INVENTORY
    contents = {
        relative: (f"{version}\n".encode() if relative == "VERSION" else f"{relative}\n".encode())
        for relative in files
    }
    install = Path(ctx.install_dir)
    for relative, content in contents.items():
        target = install / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    serving = {
        relative: hashlib.sha256(contents[relative]).hexdigest() for relative in serving_paths
    }
    receipt = payload_digest.canonical_json(
        {"schema_version": 1, "version": version, "fixture": "direct-predecessor"}
    )
    receipt_sha256 = hashlib.sha256(receipt).hexdigest()
    manifest = {
        "schema_version": 2,
        "release": version,
        "files": {
            relative: hashlib.sha256(content).hexdigest() for relative, content in contents.items()
        },
        "serving_files": serving,
        "serving_payload_sha256": payload_digest.serving_payload_sha256(serving),
        "release_receipt_sha256": receipt_sha256,
    }
    (install / inventory.MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    predecessor_receipt = install / "release-source-receipt.json"
    predecessor_receipt.write_bytes(receipt)
    (install / inventory.INSTALLED_RELEASE_STATE_FILENAME).write_bytes(
        payload_digest.canonical_json(
            {
                "schema_version": 1,
                "version": version,
                "receipt_sha256": receipt_sha256,
                "transaction_id": "fixture-direct-predecessor",
                "runtime": {"release": version},
            }
        )
    )
    return contents
