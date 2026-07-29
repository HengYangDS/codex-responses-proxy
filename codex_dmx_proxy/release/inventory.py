"""Single owner for source-install, installed-runtime, and serving inventories."""

from __future__ import annotations

from collections.abc import Mapping

from codex_dmx_proxy.release import digest

MANIFEST_FILENAME = "payload-manifest.json"
RELEASE_RECEIPT_FILENAME = "release-source-receipt.json"
INSTALLED_RELEASE_STATE_FILENAME = "release-install-state.json"
ENTRYPOINT = "codex_dmx_proxy/listener/entrypoint.py"

# Released-checkout-only files used before projection.  Together with
# ``RUNTIME_FILES`` they form the installer import closure, but these files
# deliberately never enter the installed runtime.
SOURCE_INSTALL_FILES = (
    "install.py",
    "packaging/release/publication-policy.toml",
    "codex_dmx_proxy/deployment/apply.py",
    "codex_dmx_proxy/release/publication/__init__.py",
    "codex_dmx_proxy/release/publication/evaluator.py",
    "codex_dmx_proxy/release/publication/git.py",
    "codex_dmx_proxy/release/publication/github.py",
    "codex_dmx_proxy/release/publication/gitlab.py",
    "codex_dmx_proxy/release/publication/hosted.py",
    "codex_dmx_proxy/release/admission.py",
)

SERVING_MODULES = {
    "codex_dmx_proxy/__init__.py": "codex_dmx_proxy",
    "codex_dmx_proxy/compatibility/__init__.py": "codex_dmx_proxy.compatibility",
    "codex_dmx_proxy/compatibility/empty_response.py": (
        "codex_dmx_proxy.compatibility.empty_response"
    ),
    "codex_dmx_proxy/compatibility/input_variant.py": (
        "codex_dmx_proxy.compatibility.input_variant"
    ),
    "codex_dmx_proxy/compatibility/response_failed.py": (
        "codex_dmx_proxy.compatibility.response_failed"
    ),
    "codex_dmx_proxy/listener/__init__.py": "codex_dmx_proxy.listener",
    "codex_dmx_proxy/listener/control.py": "codex_dmx_proxy.listener.control",
    "codex_dmx_proxy/listener/handoff.py": "codex_dmx_proxy.listener.handoff",
    "codex_dmx_proxy/listener/server.py": "codex_dmx_proxy.listener.server",
    "codex_dmx_proxy/listener/identity.py": "codex_dmx_proxy.listener.identity",
    "codex_dmx_proxy/listener/responses.py": "codex_dmx_proxy.listener.responses",
    "codex_dmx_proxy/listener/rewrite.py": "codex_dmx_proxy.listener.rewrite",
    "codex_dmx_proxy/listener/sse.py": "codex_dmx_proxy.listener.sse",
    "codex_dmx_proxy/listener/state.py": "codex_dmx_proxy.listener.state",
    "codex_dmx_proxy/release/__init__.py": "codex_dmx_proxy.release",
    "codex_dmx_proxy/release/digest.py": "codex_dmx_proxy.release.digest",
    "codex_dmx_proxy/release/inventory.py": "codex_dmx_proxy.release.inventory",
}
SERVING_FILES = ("VERSION", ENTRYPOINT, *SERVING_MODULES)
RUNTIME_FILES = (
    "VERSION",
    "control.py",
    "governance.py",
    "codex_dmx_proxy/__init__.py",
    "codex_dmx_proxy/errors.py",
    "codex_dmx_proxy/installation.py",
    "codex_dmx_proxy/process.py",
    "codex_dmx_proxy/python_runtime.py",
    "codex_dmx_proxy/compatibility/__init__.py",
    "codex_dmx_proxy/compatibility/empty_response.py",
    "codex_dmx_proxy/compatibility/input_variant.py",
    "codex_dmx_proxy/compatibility/response_failed.py",
    "codex_dmx_proxy/deployment/__init__.py",
    "codex_dmx_proxy/deployment/handoff.py",
    "codex_dmx_proxy/listener/__init__.py",
    "codex_dmx_proxy/listener/control.py",
    ENTRYPOINT,
    "codex_dmx_proxy/listener/handoff.py",
    "codex_dmx_proxy/listener/server.py",
    "codex_dmx_proxy/listener/identity.py",
    "codex_dmx_proxy/listener/responses.py",
    "codex_dmx_proxy/listener/rewrite.py",
    "codex_dmx_proxy/listener/sse.py",
    "codex_dmx_proxy/listener/state.py",
    "codex_dmx_proxy/release/__init__.py",
    "codex_dmx_proxy/release/digest.py",
    "codex_dmx_proxy/release/inventory.py",
    "codex_dmx_proxy/release/projection.py",
    "codex_dmx_proxy/release/transaction.py",
    "codex_dmx_proxy/route/__init__.py",
    "codex_dmx_proxy/route/management.py",
    "codex_dmx_proxy/supervision/__init__.py",
    "codex_dmx_proxy/supervision/linux.py",
    "codex_dmx_proxy/supervision/macos.py",
    "codex_dmx_proxy/supervision/select.py",
    "codex_dmx_proxy/supervision/windows.py",
    "watchdog/watchdog.py",
)


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the aggregate only for the exact serving file set."""

    if set(file_digests) != set(SERVING_FILES):
        raise digest.PayloadDigestError("serving payload files do not match the declared inventory")
    return digest.serving_payload_sha256(file_digests)
