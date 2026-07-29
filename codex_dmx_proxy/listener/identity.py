"""Freeze the exact loaded serving payload before listener startup."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from codex_dmx_proxy.release import digest, inventory

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LoadedPayloadIdentity:
    """Release and source identities captured before listener startup."""

    release: str
    serving_payload_sha256: str
    release_receipt_sha256: str
    root: Path


def freeze_loaded_payload(entrypoint: Path) -> LoadedPayloadIdentity | None:
    """Validate and freeze the manifest-owned files loaded by this process."""

    try:
        entrypoint = entrypoint.resolve(strict=True)
        root = entrypoint.parents[2]
        if entrypoint != root / inventory.ENTRYPOINT:
            return None
        manifest = _read_manifest(root / inventory.MANIFEST_FILENAME)
        raw_files = manifest.get("serving_files")
        if not isinstance(raw_files, dict) or any(
            not isinstance(path, str) or not isinstance(value, str)
            for path, value in raw_files.items()
        ):
            return None
        serving_files = cast("dict[str, str]", raw_files)
        if set(serving_files) != set(inventory.SERVING_FILES):
            return None
        paths = {inventory.ENTRYPOINT: entrypoint}
        for relative, module_name in inventory.SERVING_MODULES.items():
            module = sys.modules.get(module_name)
            if not isinstance(module, ModuleType):
                return None
            module_file = getattr(module, "__file__", None)
            if not isinstance(module_file, str):
                return None
            path = Path(module_file).resolve(strict=True)
            if path != root / relative:
                return None
            paths[relative] = path
        digests = {"VERSION": digest.sha256_file(root / "VERSION")}
        digests.update({relative: digest.sha256_file(path) for relative, path in paths.items()})
        if digests != serving_files:
            return None
        aggregate = inventory.serving_payload_sha256(digests)
        if manifest.get("serving_payload_sha256") != aggregate:
            return None
        receipt = manifest.get("release_receipt_sha256")
        if not isinstance(receipt, str) or _SHA256.fullmatch(receipt) is None:
            return None
        release = (root / "VERSION").read_text(encoding="utf-8").strip()
        if not release or manifest.get("release") != release:
            return None
        return LoadedPayloadIdentity(release, aggregate, receipt, root)
    except (
        IndexError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        digest.PayloadDigestError,
    ):
        return None


def _read_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("payload manifest must be an object")
    return value
