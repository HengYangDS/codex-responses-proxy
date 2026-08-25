"""Journal and installed-state persistence for payload transactions."""

from __future__ import annotations

import json
import re
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.json_value import JsonObject
from codex_responses_proxy.json_value import ReadOnlyJsonObject
from codex_responses_proxy.json_value import is_json_object
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
    if root.is_symlink():
        raise errors.InstallError("payload transaction root is a symbolic link")
    if not root.is_dir():
        raise errors.InstallError("payload transaction root is not a directory")
    path = journal_path(ctx)
    if path.is_symlink():
        raise errors.InstallError("payload transaction journal is a symbolic link")
    if not path.exists():
        raise errors.InstallError("payload transaction journal is missing")
    if not path.is_file():
        raise errors.InstallError("payload transaction journal is not a regular file")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise errors.InstallError("payload transaction journal could not be read") from exc
    try:
        journal = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise errors.InstallError("payload transaction journal is malformed JSON") from exc
    if not is_json_object(journal):
        raise errors.InstallError("payload transaction journal fields are invalid")
    if digest.canonical_json(journal) != content:
        raise errors.InstallError("payload transaction journal is not canonical JSON")
    if journal.get("schema_version") != TRANSACTION_JOURNAL_SCHEMA:
        raise errors.InstallError("payload transaction journal schema is unsupported")
    required = {
        "schema_version",
        "state",
        "transaction_id",
        "version",
        "receipt_sha256",
        "fresh",
    }
    allowed = required | {"reason"}
    transaction_id = journal.get("transaction_id")
    version = journal.get("version")
    receipt_sha256 = journal.get("receipt_sha256")
    fresh = journal.get("fresh")
    reason = journal.get("reason")
    if (
        not required.issubset(journal)
        or set(journal) - allowed
        or journal.get("state") not in {"prepared", "committed", "recovery_required"}
        or not isinstance(transaction_id, str)
        or not transaction_id
        or not isinstance(version, str)
        or _STRICT_VERSION.fullmatch(version) is None
        or not isinstance(receipt_sha256, str)
        or len(receipt_sha256) != 64
        or any(character not in "0123456789abcdef" for character in receipt_sha256)
        or type(fresh) is not bool
        or (reason is not None and (not isinstance(reason, str) or not reason))
        or (journal.get("state") == "recovery_required") != (reason is not None)
    ):
        raise errors.InstallError("payload transaction journal fields are invalid")
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
