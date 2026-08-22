"""Native user-command projection contracts."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import command
from tests.lifecycle.fixtures import install_context


def test_posix_command_path_uses_absolute_xdg_bin_home_or_user_local_bin(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    explicit = tmp_path / "commands"

    assert command.path(str(home), {"XDG_BIN_HOME": str(explicit)}, windows=False) == (
        explicit / "codex-responses-proxy"
    )
    assert command.path(str(home), {}, windows=False) == (
        home / ".local" / "bin" / "codex-responses-proxy"
    )
    with pytest.raises(errors.InstallError, match="XDG_BIN_HOME must be absolute"):
        command.path(str(home), {"XDG_BIN_HOME": "relative/bin"}, windows=False)


def test_windows_command_path_uses_the_user_application_alias_directory() -> None:
    home = PureWindowsPath("C:/Users/example")

    projected = command.path(
        str(home),
        {"LOCALAPPDATA": str(home / "AppData" / "Local")},
        windows=True,
    )

    assert PureWindowsPath(projected) == (
        home / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "codex-responses-proxy.exe"
    )


def assert_native_projection(command_path: Path, target: Path) -> None:
    """Assert the host-native link identifies the exact installed executable."""

    assert os.path.samefile(command_path, target)
    assert command_path.is_symlink() is (os.name != "nt")


def test_projection_replaces_only_absent_or_exact_owned_link(tmp_path: Path) -> None:
    ctx = install_context(tmp_path)
    target = Path(ctx.executable)
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / "codex-responses-proxy"

    command.project(command_path, target)
    assert_native_projection(command_path, target)

    foreign = tmp_path / "foreign"
    foreign.write_text("foreign", encoding="utf-8")
    command_path.unlink()
    command_path.symlink_to(foreign)
    with pytest.raises(errors.InstallError, match="occupied by another owner"):
        command.project(command_path, target)
    assert command_path.resolve() == foreign.resolve()


def test_restore_and_remove_preserve_a_path_that_changed_ownership(
    tmp_path: Path,
) -> None:
    target = tmp_path / "payload" / "codex-responses-proxy"
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / "codex-responses-proxy"
    snapshot = command.snapshot(command_path, target)
    command.project(command_path, target)

    command.restore(command_path, target, snapshot)
    assert not command_path.exists()

    command.project(command_path, target)
    command_path.unlink()
    command_path.write_text("foreign", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="changed ownership"):
        command.remove(command_path, target)
    assert command_path.read_text(encoding="utf-8") == "foreign"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink behavior")
def test_status_reports_exact_owned_link(tmp_path: Path) -> None:
    target = tmp_path / "payload" / "codex-responses-proxy"
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / "codex-responses-proxy"
    command.project(command_path, target)

    assert command.status(command_path, target) == {
        "state": "owned",
        "kind": "symlink",
        "path": str(command_path),
    }


def test_snapshot_round_trip_and_rejects_foreign_or_invalid_state(
    tmp_path: Path,
) -> None:
    target = tmp_path / "payload" / command.COMMAND_NAME
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / command.COMMAND_NAME

    absent = command.snapshot(command_path, target)
    command.write_snapshot(tmp_path, absent)
    assert command.read_snapshot(tmp_path) == absent

    command.project(command_path, target)
    owned = command.snapshot(command_path, target)
    command.write_snapshot(tmp_path, owned)
    assert command.read_snapshot(tmp_path) == owned

    command_path.unlink()
    command_path.write_text("foreign", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="occupied by another owner"):
        command.snapshot(command_path, target)

    invalid = tmp_path / command.SNAPSHOT_FILENAME
    invalid.write_bytes(
        command.digest.canonical_json(
            {
                "schema_version": command.SNAPSHOT_SCHEMA,
                "state": "absent",
                "kind": "symlink",
                "device": 0,
                "inode": 0,
            }
        )
    )
    with pytest.raises(errors.InstallError, match="command snapshot is invalid"):
        command.read_snapshot(tmp_path)


def test_project_rejects_invalid_target_and_reports_native_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "payload" / command.COMMAND_NAME
    command_path = tmp_path / "commands" / command.COMMAND_NAME

    with pytest.raises(errors.InstallError, match="target is not a regular file"):
        command.project(command_path, target)

    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    linked_target = tmp_path / "linked-target"
    linked_target.symlink_to(target)
    with pytest.raises(errors.InstallError, match="target is not a regular file"):
        command.project(command_path, linked_target)

    def fail_projection(_target: Path, _link: Path) -> None:
        raise OSError("projection unavailable")

    primitive = "link" if os.name == "nt" else "symlink"
    monkeypatch.setattr(command.os, primitive, fail_projection)
    with pytest.raises(errors.InstallError, match="native command projection failed"):
        command.project(command_path, target)
    assert not list(command_path.parent.glob(".*.tmp-*"))


def test_project_uses_a_native_hardlink_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "payload" / f"{command.COMMAND_NAME}.exe"
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / f"{command.COMMAND_NAME}.exe"
    real_link = os.link
    calls: list[tuple[Path, Path]] = []

    def record_link(source: Path, destination: Path) -> None:
        calls.append((source, destination))
        real_link(source, destination)

    monkeypatch.setattr(
        command,
        "os",
        SimpleNamespace(
            name="nt",
            getpid=os.getpid,
            link=record_link,
            path=os.path,
            replace=os.replace,
            symlink=os.symlink,
        ),
    )

    command.project(command_path, target)

    assert calls[0][0] == target
    assert os.path.samefile(command_path, target)
    assert command.status(command_path, target) == {
        "state": "owned",
        "kind": "hardlink",
        "path": str(command_path),
    }


def test_project_requires_post_projection_ownership_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "payload" / command.COMMAND_NAME
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / command.COMMAND_NAME
    observations = iter((("absent", ""), ("foreign", "")))
    monkeypatch.setattr(command, "_classify", lambda *_args: next(observations))

    with pytest.raises(errors.InstallError, match="ownership is unproved"):
        command.project(command_path, target)


def test_detach_handles_absence_snapshot_ownership_and_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "payload" / command.COMMAND_NAME
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / command.COMMAND_NAME
    absent = command.snapshot(command_path, target)
    command.detach(command_path, target, absent)

    command_path.parent.mkdir(parents=True)
    command_path.write_text("prior owner", encoding="utf-8")
    metadata = command_path.lstat()
    prior = command.Snapshot(
        state="owned", kind="symlink", device=metadata.st_dev, inode=metadata.st_ino
    )
    command.detach(command_path, target, prior)
    assert not command_path.exists()

    command_path.write_text("changed owner", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="changed ownership"):
        command.detach(command_path, target, replace(prior, device=-1))

    command_path.unlink()
    command.project(command_path, target)
    real_unlink = Path.unlink

    def fail_owned_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == command_path:
            raise OSError("busy")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_owned_unlink)
    with pytest.raises(errors.InstallError, match="native command removal failed"):
        command.detach(command_path, target, command.snapshot(command_path, target))


def test_restore_and_remove_cover_owned_absent_and_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "payload" / command.COMMAND_NAME
    target.parent.mkdir(parents=True)
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "commands" / command.COMMAND_NAME

    command.project(command_path, target)
    owned = command.snapshot(command_path, target)
    command.restore(command_path, target, owned)
    assert_native_projection(command_path, target)
    assert command.remove(command_path, target) is True
    assert command.remove(command_path, target) is False

    command.project(command_path, target)
    real_unlink = Path.unlink

    def fail_owned_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == command_path:
            raise OSError("busy")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_owned_unlink)
    with pytest.raises(errors.InstallError, match="native command removal failed"):
        command.remove(command_path, target)


def test_classification_and_snapshot_matching_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_text("runtime", encoding="utf-8")
    command_path = tmp_path / "command"
    command_path.write_text("foreign", encoding="utf-8")

    assert command._classify(command_path, target) == ("foreign", "")
    monkeypatch.setattr(
        command.os.path, "samefile", lambda *_args: (_ for _ in ()).throw(OSError())
    )
    assert command._classify(command_path, target) == ("foreign", "")

    assert command._matches_snapshot(command_path, None) is False
    assert command._matches_snapshot(command_path, command.Snapshot(state="absent")) is False
    metadata = command_path.lstat()
    owned = command.Snapshot(
        state="owned", kind="hardlink", device=metadata.st_dev, inode=metadata.st_ino
    )
    assert command._matches_snapshot(command_path, owned) is True
    assert command._matches_snapshot(command_path, replace(owned, inode=owned.inode + 1)) is False

    real_lstat = Path.lstat

    def fail_lstat(self: Path) -> os.stat_result:
        if self == command_path:
            raise OSError("unavailable")
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", fail_lstat)
    assert command._matches_snapshot(command_path, owned) is False
