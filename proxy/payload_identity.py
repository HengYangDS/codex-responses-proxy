"""Startup-frozen release and aggregate identity for the loaded proxy payload.

The entrypoint supplies the exact module objects imported by the serving
process.  This module accepts them only when every file resolves below the same
payload root and exactly matches the manifest-owned serving file set.  Identity
is computed from the bytes those module paths name at startup and is then held
in memory for the lifetime of the process.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast


MANIFEST_FILENAME = "payload-manifest.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LoadedPayloadIdentity:
    """Release and aggregate digest captured before the listener starts."""

    release: str
    serving_payload_sha256: str
    release_receipt_sha256: str
    root: Path


def freeze_loaded_payload(
    entrypoint: Path,
    modules: Mapping[str, ModuleType],
) -> LoadedPayloadIdentity | None:
    """Freeze identity only for an exact, same-root, manifest-owned module set."""
    try:
        entrypoint = entrypoint.resolve(strict=True)
        root = entrypoint.parents[1]
        manifest = _read_manifest(root / MANIFEST_FILENAME)
        raw_serving_files = manifest["serving_files"]
        if not isinstance(raw_serving_files, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in raw_serving_files.items()
        ):
            return None
        serving_files = cast("dict[str, str]", raw_serving_files)
        expected = {str(relative) for relative in serving_files}
        actual = {"VERSION", "proxy/dmx_responses_proxy.py", *modules}
        if expected != actual:
            return None
        paths = {"proxy/dmx_responses_proxy.py": entrypoint}
        for relative, module in modules.items():
            module_file = getattr(module, "__file__", None)
            if not isinstance(module_file, str):
                return None
            path = Path(module_file).resolve(strict=True)
            if path != root / relative:
                return None
            paths[relative] = path
        digests = {"VERSION": _sha256_file(root / "VERSION")}
        digests.update({relative: _sha256_file(path) for relative, path in paths.items()})
        if any(serving_files.get(relative) != digest for relative, digest in digests.items()):
            return None
        aggregate = _aggregate(digests)
        if manifest.get("serving_payload_sha256") != aggregate:
            return None
        receipt = manifest.get("release_receipt_sha256")
        if not isinstance(receipt, str) or _SHA256.fullmatch(receipt) is None:
            return None
        release = (root / "VERSION").read_text(encoding="utf-8").strip()
        if not release or manifest.get("release") != release:
            return None
        return LoadedPayloadIdentity(release, aggregate, receipt, root)
    except (IndexError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def freeze_release(entrypoint: Path) -> str:
    """Capture the nearest packaged VERSION exactly once for this process."""
    resolved = entrypoint.resolve()
    for candidate in (resolved.parents[1] / "VERSION", resolved.parents[2] / "VERSION"):
        try:
            release = candidate.read_text(encoding="utf-8").strip()
        except (IndexError, OSError):
            continue
        if release:
            return release
    return "0+unknown"


def _read_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("payload manifest must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _aggregate(file_digests: Mapping[str, str]) -> str:
    aggregate = hashlib.sha256()
    for relative in sorted(file_digests):
        path_bytes = relative.encode("utf-8")
        digest_bytes = bytes.fromhex(file_digests[relative])
        aggregate.update(len(path_bytes).to_bytes(8, "big"))
        aggregate.update(path_bytes)
        aggregate.update(len(digest_bytes).to_bytes(8, "big"))
        aggregate.update(digest_bytes)
    return aggregate.hexdigest()
