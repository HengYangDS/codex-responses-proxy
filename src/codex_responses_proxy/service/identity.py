"""Freeze the exact loaded serving payload before listener startup."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from codex_responses_proxy.service import digest, inventory

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_PAYLOAD_FIELDS = {
    "release": "release",
    "serving_payload_sha256": "serving_payload_sha256",
    "release_receipt_sha256": "release_receipt_sha256",
    "payload_manifest_sha256": "manifest_sha256",
}


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


def runtime_payload_matches(runtime: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    """Match one runtime snapshot to the canonical payload identity fields."""

    return all(
        runtime.get(runtime_field) == expected.get(expected_field)
        for runtime_field, expected_field in _RUNTIME_PAYLOAD_FIELDS.items()
    )


def freeze_loaded_payload(executable: Path) -> LoadedPayloadIdentity | None:
    """Validate and freeze the manifest-owned files loaded by this process."""

    try:
        executable = executable.resolve(strict=True)
        root = executable.parents[1]
        if executable not in {
            root / inventory.EXECUTABLE,
            root / inventory.WINDOWS_EXECUTABLE,
        }:
            return None
        manifest = _read_manifest(root / inventory.MANIFEST_FILENAME)
        raw_files = manifest.get("serving_files")
        if not isinstance(raw_files, dict) or any(
            not isinstance(path, str) or not isinstance(value, str)
            for path, value in raw_files.items()
        ):
            return None
        serving_files = cast("dict[str, str]", raw_files)
        executable_relative = executable.relative_to(root).as_posix()
        expected_files = set(serving_files)
        windows = executable_relative == inventory.WINDOWS_EXECUTABLE
        if not inventory.required_runtime_files(windows=windows).issubset(expected_files) or any(
            not inventory.is_runtime_file(path, windows=windows) for path in expected_files
        ):
            return None
        digests = {path: digest.sha256_file(root / path) for path in serving_files}
        if digests != serving_files:
            return None
        aggregate = inventory.serving_payload_sha256(digests)
        if manifest.get("serving_payload_sha256") != aggregate:
            return None
        receipt = manifest.get("release_receipt_sha256")
        if not isinstance(receipt, str) or _SHA256.fullmatch(receipt) is None:
            return None
        release = manifest.get("release")
        if not isinstance(release, str) or not release:
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


def committed_payload(executable: Path) -> LoadedPayloadIdentity | None:
    """Return the complete successor identity currently committed on disk."""

    try:
        executable = executable.resolve(strict=True)
        root = executable.parents[1]
        if executable not in {
            root / inventory.EXECUTABLE,
            root / inventory.WINDOWS_EXECUTABLE,
        }:
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
        executable_relative = executable.relative_to(root).as_posix()
        expected_files = set(files)
        windows = executable_relative == inventory.WINDOWS_EXECUTABLE
        if (
            set(serving) != expected_files
            or not inventory.required_runtime_files(windows=windows).issubset(expected_files)
            or any(not inventory.is_runtime_file(path, windows=windows) for path in expected_files)
        ):
            raise ValueError("installed inventory mismatch")
        if any(digest.sha256_file(root / path) != expected for path, expected in files.items()):
            raise ValueError("installed payload digest mismatch")
        if any(files[path] != expected for path, expected in serving.items()):
            raise ValueError("serving digest mismatch")
        aggregate = digest.serving_payload_sha256(serving)
        receipt = cast("str", manifest["release_receipt_sha256"])
        release = manifest.get("release")
        if (
            not isinstance(release, str)
            or not release
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
    except (
        IndexError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        digest.PayloadDigestError,
    ):
        return None


def _read_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("payload manifest must be an object")
    return value
