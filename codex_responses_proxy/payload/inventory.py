"""Single owner for source-install, installed-runtime, and serving inventories."""

from __future__ import annotations

from collections.abc import Mapping

from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.payload import digest

MANIFEST_FILENAME = "payload-manifest.json"
RELEASE_RECEIPT_FILENAME = "release-source-receipt.json"
INSTALLED_RELEASE_STATE_FILENAME = "release-install-state.json"
ENTRYPOINT = "codex_responses_proxy/listener/entrypoint.py"
PROVIDER_MANIFEST = "codex_responses_proxy/providers/manifest.toml"
POLICY_ROOT = "codex_responses_proxy/providers/policies"


def _provider_policy_files() -> tuple[str, ...]:
    """Derive released wire-policy files from the validated provider manifest."""

    package_prefix = provider_registry.POLICY_PACKAGE + "."
    files = []
    manifest = provider_registry.load(provider_registry.default_manifest_path())
    for module_name in provider_registry.policy_module_names(manifest):
        if not module_name.startswith(package_prefix):
            raise RuntimeError("provider manifest references an external policy module")
        relative = module_name.replace(".", "/") + ".py"
        files.append(relative)
    return tuple(files)


POLICY_FILES = _provider_policy_files()

# Signed-source-only files used before projection.  Together with
# ``RUNTIME_FILES`` they form the installer import closure, but these files
# deliberately never enter the installed runtime.  Forge publication tooling
# is not part of installation.
SOURCE_INSTALL_FILES = (
    "codex_responses_proxy/commands/install.py",
    "codex_responses_proxy/deployment/apply.py",
    "codex_responses_proxy/release/admission.py",
)

SERVING_MODULES = {
    "codex_responses_proxy/__init__.py": "codex_responses_proxy",
    "codex_responses_proxy/payload/__init__.py": "codex_responses_proxy.payload",
    "codex_responses_proxy/payload/digest.py": "codex_responses_proxy.payload.digest",
    "codex_responses_proxy/payload/identity.py": "codex_responses_proxy.payload.identity",
    "codex_responses_proxy/payload/inventory.py": "codex_responses_proxy.payload.inventory",
    "codex_responses_proxy/recovery/__init__.py": "codex_responses_proxy.recovery",
    "codex_responses_proxy/recovery/input_variant.py": (
        "codex_responses_proxy.recovery.input_variant"
    ),
    "codex_responses_proxy/recovery/response_failed.py": (
        "codex_responses_proxy.recovery.response_failed"
    ),
    "codex_responses_proxy/listener/__init__.py": "codex_responses_proxy.listener",
    "codex_responses_proxy/listener/control.py": "codex_responses_proxy.listener.control",
    "codex_responses_proxy/listener/handoff/__init__.py": (
        "codex_responses_proxy.listener.handoff"
    ),
    "codex_responses_proxy/listener/handoff/protocol.py": (
        "codex_responses_proxy.listener.handoff.protocol"
    ),
    "codex_responses_proxy/listener/handoff/transaction.py": (
        "codex_responses_proxy.listener.handoff.transaction"
    ),
    "codex_responses_proxy/listener/server.py": "codex_responses_proxy.listener.server",
    "codex_responses_proxy/replay/__init__.py": "codex_responses_proxy.replay",
    "codex_responses_proxy/replay/response.py": "codex_responses_proxy.replay.response",
    "codex_responses_proxy/replay/request.py": "codex_responses_proxy.replay.request",
    "codex_responses_proxy/transport/__init__.py": "codex_responses_proxy.transport",
    "codex_responses_proxy/transport/exchange.py": "codex_responses_proxy.transport.exchange",
    "codex_responses_proxy/transport/relay.py": "codex_responses_proxy.transport.relay",
    "codex_responses_proxy/transport/responses.py": "codex_responses_proxy.transport.responses",
    "codex_responses_proxy/transport/sse.py": "codex_responses_proxy.transport.sse",
    "codex_responses_proxy/providers/__init__.py": "codex_responses_proxy.providers",
    "codex_responses_proxy/providers/policies/__init__.py": (
        "codex_responses_proxy.providers.policies"
    ),
    **{relative: relative.removesuffix(".py").replace("/", ".") for relative in POLICY_FILES},
    "codex_responses_proxy/providers/registry.py": "codex_responses_proxy.providers.registry",
    "codex_responses_proxy/runtime/__init__.py": "codex_responses_proxy.runtime",
    "codex_responses_proxy/runtime/admission.py": "codex_responses_proxy.runtime.admission",
    "codex_responses_proxy/runtime/config.py": "codex_responses_proxy.runtime.config",
    "codex_responses_proxy/runtime/operational_log.py": "codex_responses_proxy.runtime.operational_log",
    "codex_responses_proxy/runtime/telemetry.py": "codex_responses_proxy.runtime.telemetry",
    "codex_responses_proxy/transport/cooldown.py": "codex_responses_proxy.transport.cooldown",
}
SERVING_FILES = ("VERSION", PROVIDER_MANIFEST, ENTRYPOINT, *SERVING_MODULES)
RUNTIME_FILES = (
    "VERSION",
    PROVIDER_MANIFEST,
    "codex_responses_proxy/commands/control.py",
    "codex_responses_proxy/commands/__init__.py",
    "codex_responses_proxy/__init__.py",
    "codex_responses_proxy/errors.py",
    "codex_responses_proxy/runtime/context.py",
    "codex_responses_proxy/supervision/process.py",
    "codex_responses_proxy/supervision/python.py",
    "codex_responses_proxy/recovery/__init__.py",
    "codex_responses_proxy/recovery/input_variant.py",
    "codex_responses_proxy/recovery/response_failed.py",
    "codex_responses_proxy/deployment/__init__.py",
    "codex_responses_proxy/deployment/handoff.py",
    "codex_responses_proxy/listener/__init__.py",
    "codex_responses_proxy/listener/control.py",
    ENTRYPOINT,
    "codex_responses_proxy/listener/handoff/__init__.py",
    "codex_responses_proxy/listener/handoff/protocol.py",
    "codex_responses_proxy/listener/handoff/transaction.py",
    "codex_responses_proxy/listener/server.py",
    "codex_responses_proxy/payload/__init__.py",
    "codex_responses_proxy/payload/identity.py",
    "codex_responses_proxy/transport/__init__.py",
    "codex_responses_proxy/transport/exchange.py",
    "codex_responses_proxy/transport/relay.py",
    "codex_responses_proxy/transport/responses.py",
    "codex_responses_proxy/replay/__init__.py",
    "codex_responses_proxy/replay/response.py",
    "codex_responses_proxy/replay/request.py",
    "codex_responses_proxy/transport/sse.py",
    "codex_responses_proxy/transport/cooldown.py",
    "codex_responses_proxy/providers/__init__.py",
    "codex_responses_proxy/providers/policies/__init__.py",
    *POLICY_FILES,
    "codex_responses_proxy/providers/registry.py",
    "codex_responses_proxy/payload/digest.py",
    "codex_responses_proxy/payload/inventory.py",
    "codex_responses_proxy/payload/owned_files.py",
    "codex_responses_proxy/runtime/__init__.py",
    "codex_responses_proxy/runtime/admission.py",
    "codex_responses_proxy/runtime/config.py",
    "codex_responses_proxy/runtime/operational_log.py",
    "codex_responses_proxy/runtime/telemetry.py",
    "codex_responses_proxy/payload/projection.py",
    "codex_responses_proxy/payload/source.py",
    "codex_responses_proxy/payload/candidate.py",
    "codex_responses_proxy/payload/migration.py",
    "codex_responses_proxy/payload/rollback.py",
    "codex_responses_proxy/payload/transaction.py",
    "codex_responses_proxy/payload/state.py",
    "codex_responses_proxy/supervision/__init__.py",
    "codex_responses_proxy/supervision/linux.py",
    "codex_responses_proxy/supervision/macos.py",
    "codex_responses_proxy/supervision/native_service.py",
    "codex_responses_proxy/supervision/windows.py",
    "codex_responses_proxy/supervision/watchdog.py",
)


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the aggregate only for the exact serving file set."""

    if set(file_digests) != set(SERVING_FILES):
        raise digest.PayloadDigestError("serving payload files do not match the declared inventory")
    return digest.serving_payload_sha256(file_digests)
