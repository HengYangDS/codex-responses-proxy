"""Journal and installed-state persistence for payload transactions."""

from __future__ import annotations

import re
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.json_value import JsonObject
from codex_responses_proxy.json_value import ReadOnlyJsonObject
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import inventory

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
    root = transaction_root(ctx)
    if not root.exists() and not root.is_symlink():
        return None
    try:
        journal = read_journal(ctx)
    except errors.InstallError as exc:
        return {"state": "invalid", "detail": str(exc)}
    allowed = ("transaction_id", "version", "receipt_sha256", "state", "fresh")
    return {key: journal[key] for key in allowed if key in journal}


def read_journal(ctx: runtime_context.RuntimeContext) -> JsonObject:
    """Read one existing transaction through its strict current schema."""
    root = transaction_root(ctx)
    if root.is_symlink() or not root.is_dir():
        raise errors.InstallError("payload transaction root is invalid")
    path = journal_path(ctx)
    if path.is_symlink():
        raise errors.InstallError("payload transaction journal is invalid")
    if not path.is_file():
        raise errors.InstallError("payload transaction journal is missing")
    journal = owned_files.read_canonical_json(path, "payload transaction journal")
    if (
        journal.get("schema_version") != TRANSACTION_JOURNAL_SCHEMA
        or journal.get("state") not in {"prepared", "committed", "recovery_required"}
        or not isinstance(journal.get("transaction_id"), str)
        or not isinstance(journal.get("version"), str)
        or not isinstance(journal.get("receipt_sha256"), str)
        or not isinstance(journal.get("fresh"), bool)
    ):
        raise errors.InstallError("payload transaction journal is invalid")
    return journal


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
    journal: JsonObject = {
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


def read_installed(ctx: runtime_context.RuntimeContext) -> JsonObject | None:
    """Read and validate the installed release state when present."""
    path = installed_path(ctx)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise errors.InstallError("installed release state is invalid")
    state = owned_files.read_canonical_json(path, "installed release state")
    if state.get("schema_version") != INSTALLED_RELEASE_STATE_SCHEMA:
        raise errors.InstallError("installed release state schema is unsupported")
    receipt_sha256 = state.get("receipt_sha256")
    if (
        not isinstance(state.get("transaction_id"), str)
        or not state["transaction_id"]
        or not isinstance(receipt_sha256, str)
        or len(receipt_sha256) != 64
        or any(character not in "0123456789abcdef" for character in receipt_sha256)
        or not isinstance(state.get("runtime"), dict)
    ):
        raise errors.InstallError("installed release state is invalid")
    require_version(state)
    require_command(state)
    return state


def require_version(state: ReadOnlyJsonObject) -> str:
    """Return a strict installed-state version."""
    version = state.get("version")
    if not isinstance(version, str) or _STRICT_VERSION.fullmatch(version) is None:
        raise errors.InstallError("installed release state version is invalid")
    return version


def require_command(state: ReadOnlyJsonObject) -> str:
    """Return the absolute command path recorded at installation."""
    command = state.get("command")
    if not isinstance(command, str) or not command or not Path(command).is_absolute():
        raise errors.InstallError("installed release state command path is invalid")
    return command


def compare_versions(left: str, right: str) -> int:
    """Compare two already validated semantic versions."""
    versions = tuple(tuple(map(int, version.split("."))) for version in (left, right))
    return (versions[0] > versions[1]) - (versions[0] < versions[1])
