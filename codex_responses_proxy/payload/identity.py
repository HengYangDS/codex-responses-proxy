"""Freeze the exact loaded serving payload before listener startup."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from codex_responses_proxy.payload import digest, inventory

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LoadedPayloadIdentity:
    """Release and source identities captured before listener startup."""

    release: str
    serving_payload_sha256: str
    release_receipt_sha256: str
    manifest_sha256: str
    root: Path

    def handoff(self) -> dict[str, str]:
        """Return the fields exchanged by protocol-v2 handoff."""

        return {
            "release": self.release,
            "serving_payload_sha256": self.serving_payload_sha256,
            "release_receipt_sha256": self.release_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
        }


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
        digests = {
            "VERSION": digest.sha256_file(root / "VERSION"),
            "codex_responses_proxy/providers/manifest.toml": digest.sha256_file(
                root / "codex_responses_proxy/providers/manifest.toml"
            ),
        }
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
        return LoadedPayloadIdentity(
            release,
            aggregate,
            receipt,
            digest.sha256_file(root / inventory.MANIFEST_FILENAME),
            root,
        )
    except (
        IndexError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        digest.PayloadDigestError,
    ):
        return None


def committed_payload(entrypoint: Path) -> LoadedPayloadIdentity | None:
    """Return the complete successor identity currently committed on disk."""

    try:
        entrypoint = entrypoint.resolve(strict=True)
        root = entrypoint.parents[2]
        if entrypoint != root / inventory.ENTRYPOINT:
            return None
        manifest = _read_manifest(root / inventory.MANIFEST_FILENAME)
        if manifest.get("schema_version") != 2:
            raise ValueError("installed manifest schema mismatch")
        raw_files = manifest.get("files")
        raw_serving = manifest.get("serving_files")
        if not isinstance(raw_files, dict) or not isinstance(raw_serving, dict):
            raise ValueError("installed manifest digest mapping is invalid")
        files = cast("dict[str, str]", raw_files)
        serving = cast("dict[str, str]", raw_serving)
        if any(
            not isinstance(path, str) or not isinstance(expected, str)
            for mapping in (files, serving)
            for path, expected in mapping.items()
        ):
            raise ValueError("installed manifest digest mapping is invalid")
        if set(files) != set(inventory.RUNTIME_FILES) or set(serving) != set(
            inventory.SERVING_FILES
        ):
            raise ValueError("installed inventory mismatch")
        if any(digest.sha256_file(root / path) != expected for path, expected in files.items()):
            raise ValueError("installed payload digest mismatch")
        if any(files[path] != expected for path, expected in serving.items()):
            raise ValueError("serving digest mismatch")
        aggregate = inventory.serving_payload_sha256(serving)
        receipt = cast("str", manifest["release_receipt_sha256"])
        release = (root / "VERSION").read_text(encoding="utf-8").strip()
        if (
            manifest.get("release") != release
            or manifest.get("serving_payload_sha256") != aggregate
            or _SHA256.fullmatch(receipt) is None
            or digest.sha256_file(root / inventory.RELEASE_RECEIPT_FILENAME) != receipt
        ):
            raise ValueError("installed successor identity mismatch")
        return LoadedPayloadIdentity(
            release,
            aggregate,
            receipt,
            digest.sha256_file(root / inventory.MANIFEST_FILENAME),
            root,
        )
    except (IndexError, KeyError, OSError, TypeError, ValueError, digest.PayloadDigestError):
        return None


def _read_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("payload manifest must be an object")
    return value
