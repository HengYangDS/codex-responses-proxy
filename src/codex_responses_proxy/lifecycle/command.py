"""Native user-command path and exact link ownership."""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.service import digest

COMMAND_NAME = "codex-responses-proxy"
SNAPSHOT_FILENAME = "command.json"
SNAPSHOT_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Pre-transaction command-path state."""

    state: str
    kind: str = ""
    device: int = 0
    inode: int = 0


def path(home: str, environment: Mapping[str, str], *, windows: bool) -> Path:
    """Return the current user's platform-native command path."""

    if windows:
        local = environment.get("LOCALAPPDATA") or str(PureWindowsPath(home) / "AppData" / "Local")
        return Path(
            str(PureWindowsPath(local) / "Microsoft" / "WindowsApps" / f"{COMMAND_NAME}.exe")
        )
    configured = environment.get("XDG_BIN_HOME")
    if configured:
        directory = Path(configured).expanduser()
        if not directory.is_absolute():
            raise errors.InstallError("XDG_BIN_HOME must be absolute")
    else:
        directory = Path(home) / ".local" / "bin"
    return directory / COMMAND_NAME


def snapshot(command_path: Path, target: Path) -> Snapshot:
    """Prove the command path is absent or owned before payload mutation."""

    state, kind = _classify(command_path, target)
    if state == "foreign":
        raise errors.InstallError(f"command path is occupied by another owner: {command_path}")
    if state == "absent":
        return Snapshot(state="absent")
    metadata = command_path.lstat()
    return Snapshot(
        state="owned",
        kind=kind,
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def write_snapshot(root: Path, value: Snapshot) -> None:
    """Persist the command rollback fact beside the payload snapshot."""

    owned_files.write_bytes(
        root / SNAPSHOT_FILENAME,
        digest.canonical_json(
            {
                "schema_version": SNAPSHOT_SCHEMA,
                "state": value.state,
                "kind": value.kind,
                "device": value.device,
                "inode": value.inode,
            }
        ),
        mode=0o600,
    )


def read_snapshot(root: Path) -> Snapshot:
    """Read one canonical command rollback fact."""

    value = owned_files.read_canonical_json(root / SNAPSHOT_FILENAME, "command snapshot")
    if (
        value.get("schema_version") != SNAPSHOT_SCHEMA
        or value.get("state") not in {"absent", "owned"}
        or value.get("kind") not in {"", "symlink", "hardlink"}
        or type(value.get("device")) is not int
        or type(value.get("inode")) is not int
        or (value["state"] == "absent" and any((value["kind"], value["device"], value["inode"])))
        or (value["state"] == "owned" and not all((value["kind"], value["device"], value["inode"])))
    ):
        raise errors.InstallError("command snapshot is invalid")
    return Snapshot(
        state=value["state"],
        kind=value["kind"],
        device=value["device"],
        inode=value["inode"],
    )


def project(command_path: Path, target: Path, previous: Snapshot | None = None) -> None:
    """Atomically project the installed executable through one native link."""

    if target.is_symlink() or not target.is_file():
        raise errors.InstallError("installed command target is not a regular file")
    state, _kind = _classify(command_path, target)
    if state == "foreign" and not _matches_snapshot(command_path, previous):
        raise errors.InstallError(f"command path is occupied by another owner: {command_path}")
    command_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = command_path.with_name(f".{command_path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        if os.name == "nt":
            os.link(target, temporary)
        else:
            os.symlink(target, temporary)
        os.replace(temporary, command_path)
    except OSError as exc:
        raise errors.InstallError(f"native command projection failed: {command_path}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    if _classify(command_path, target)[0] != "owned":
        raise errors.InstallError("native command projection ownership is unproved")


def detach(command_path: Path, target: Path, previous: Snapshot) -> None:
    """Remove only the current candidate link or the proved prior link."""

    state, _kind = _classify(command_path, target)
    if state == "absent":
        return
    if state == "foreign" and not _matches_snapshot(command_path, previous):
        raise errors.InstallError(f"command path changed ownership: {command_path}")
    try:
        command_path.unlink()
    except OSError as exc:
        raise errors.InstallError(f"native command removal failed: {command_path}") from exc


def restore(command_path: Path, target: Path, previous: Snapshot) -> None:
    """Restore the exact prior link state after payload restoration."""

    state, _kind = _classify(command_path, target)
    if state == "foreign":
        raise errors.InstallError(f"command path changed ownership: {command_path}")
    if state == "owned":
        command_path.unlink()
    if previous.state == "owned":
        project(command_path, target)


def remove(command_path: Path, target: Path) -> bool:
    """Remove only a live command link still owned by this payload."""

    state, _kind = _classify(command_path, target)
    if state == "absent":
        return False
    if state == "foreign":
        raise errors.InstallError(f"command path changed ownership: {command_path}")
    try:
        command_path.unlink()
    except OSError as exc:
        raise errors.InstallError(f"native command removal failed: {command_path}") from exc
    return True


def status(command_path: Path, target: Path) -> dict[str, object]:
    """Return one read-only command discoverability result."""

    state, _kind = _classify(command_path, target)
    return {
        "path": str(command_path),
        "available": state == "owned",
        "owned": state == "owned",
    }


def _classify(command_path: Path, target: Path) -> tuple[str, str]:
    if not os.path.lexists(command_path):
        return "absent", ""
    try:
        if command_path.is_symlink():
            return (
                ("owned", "symlink")
                if command_path.resolve(strict=False) == target.resolve(strict=False)
                else ("foreign", "")
            )
        if command_path.is_file() and target.is_file() and os.path.samefile(command_path, target):
            return "owned", "hardlink"
    except OSError:
        pass
    return "foreign", ""


def _matches_snapshot(command_path: Path, previous: Snapshot | None) -> bool:
    if previous is None or previous.state != "owned" or not os.path.lexists(command_path):
        return False
    try:
        metadata = command_path.lstat()
    except OSError:
        return False
    return metadata.st_dev == previous.device and metadata.st_ino == previous.inode
