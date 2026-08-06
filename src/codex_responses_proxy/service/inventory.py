"""Single owner for native installed-runtime identity."""

from __future__ import annotations

from collections.abc import Mapping

from codex_responses_proxy.runtime import config
from codex_responses_proxy.service import digest

MANIFEST_FILENAME = "payload-manifest.json"
RELEASE_RECEIPT_FILENAME = "release-asset-receipt.json"
INSTALLED_RELEASE_STATE_FILENAME = "release-install-state.json"
PROVIDER_MANIFEST = "providers.toml"
EXECUTABLE = "bin/codex-responses-proxy"
WINDOWS_EXECUTABLE = "bin/codex-responses-proxy.exe"
RUNTIME_FILES = (EXECUTABLE, PROVIDER_MANIFEST)
SERVING_FILES = RUNTIME_FILES


def executable_name(*, windows: bool = False) -> str:
    """Return the platform archive member owned by the runtime."""

    return WINDOWS_EXECUTABLE if windows else EXECUTABLE


def runtime_files(*, windows: bool = False) -> tuple[str, str]:
    """Return the exact installed file set for one native platform."""

    return executable_name(windows=windows), PROVIDER_MANIFEST


def installed_executable(root: str, *, windows: bool = False) -> str:
    """Return the platform executable below an installed data root."""

    return config.path_join(root, *executable_name(windows=windows).split("/"))


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the aggregate only for the exact serving file set."""

    if (
        len(file_digests) != 2
        or PROVIDER_MANIFEST not in file_digests
        or not set(file_digests).intersection({EXECUTABLE, WINDOWS_EXECUTABLE})
    ):
        raise digest.PayloadDigestError("serving payload files do not match the declared inventory")
    return digest.serving_payload_sha256(file_digests)
