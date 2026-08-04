"""Journal and installed-state persistence for payload transactions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.service import digest, inventory
from codex_responses_proxy.lifecycle import owned_files

TRANSACTION_JOURNAL_FILENAME = "transaction.json"
INSTALLED_RELEASE_STATE_SCHEMA = 1
TRANSACTION_JOURNAL_SCHEMA = 1
_STRICT_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def transaction_root(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the sibling directory used for payload transactions."""
    return Path(f"{ctx.install_dir}.transaction")


def installed_path(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the finalized released-projection state path."""
    return Path(ctx.install_dir, inventory.INSTALLED_RELEASE_STATE_FILENAME)


def journal_path(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the active payload transaction journal path."""
    return transaction_root(ctx) / TRANSACTION_JOURNAL_FILENAME


def status(ctx: runtime_context.RuntimeContext) -> dict[str, object] | None:
    """Return the bounded identity of one active transaction."""
    path = journal_path(ctx)
    if not path.exists():
        return None
    journal = owned_files.read_canonical_json(path, "payload transaction journal")
    allowed = ("transaction_id", "version", "receipt_sha256", "state", "fresh")
    return {key: journal[key] for key in allowed if key in journal}


def write_journal(
    ctx: runtime_context.RuntimeContext,
    *,
    transaction_id: str,
    version: str,
    receipt_sha256: str,
    state: str,
    fresh: bool,
    reason: str | None = None,
) -> None:
    """Write one canonical secret-free transaction journal."""
    journal: dict[str, Any] = {
        "schema_version": TRANSACTION_JOURNAL_SCHEMA,
        "transaction_id": transaction_id,
        "version": version,
        "receipt_sha256": receipt_sha256,
        "state": state,
        "fresh": fresh,
    }
    if reason is not None:
        journal["reason"] = reason
    owned_files.write_bytes(journal_path(ctx), digest.canonical_json(journal), mode=0o600)


def read_installed(ctx: runtime_context.RuntimeContext) -> dict[str, Any] | None:
    """Read and validate the installed release state when present."""
    path = installed_path(ctx)
    if not path.exists():
        return None
    state = owned_files.read_canonical_json(path, "installed release state")
    if state.get("schema_version") != INSTALLED_RELEASE_STATE_SCHEMA:
        raise errors.InstallError("installed release state schema is unsupported")
    return state


def require_version(state: Mapping[str, Any]) -> str:
    """Return a strict installed-state version."""
    version = state.get("version")
    if not isinstance(version, str) or _STRICT_VERSION.fullmatch(version) is None:
        raise errors.InstallError("installed release state version is invalid")
    return version


def compare_versions(left: str, right: str) -> int:
    """Compare two already validated semantic versions."""
    versions = tuple(tuple(map(int, version.split("."))) for version in (left, right))
    return (versions[0] > versions[1]) - (versions[0] < versions[1])
