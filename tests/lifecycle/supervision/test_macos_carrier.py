"""macOS launch-agent files retain exact ownership through native transitions."""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle.supervision import macos
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.supervision.fixtures import completed


@pytest.fixture
def carrier_context(tmp_path, mocker):
    ctx = install_context(tmp_path / "owned")
    Path(ctx.user_home).mkdir(parents=True)
    mocker.patch.object(macos, "_native_tool", side_effect=lambda name: name)
    mocker.patch.object(
        macos, "_registered_service", return_value=("user/501", macos._Service(False, None))
    )
    return ctx


@pytest.mark.skipif(os.name == "nt", reason="POSIX symbolic-link ownership")
@pytest.mark.parametrize("indirect", ["leaf", "library", "agents"])
def test_install_preserves_every_indirect_carrier_target(
    indirect, carrier_context, tmp_path, mocker
) -> None:
    ctx = carrier_context
    carrier = Path(macos._plist_path(ctx))
    outside = tmp_path / "outside"
    outside.mkdir()
    if indirect == "leaf":
        carrier.parent.mkdir(parents=True)
        foreign = outside / "carrier.plist"
        carrier.symlink_to(foreign)
    else:
        parent = carrier.parent.parent if indirect == "library" else carrier.parent
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.symlink_to(outside, target_is_directory=True)
        foreign = outside / (
            "LaunchAgents/" + carrier.name if indirect == "library" else carrier.name
        )
        foreign.parent.mkdir(parents=True, exist_ok=True)
    before = b"unowned external carrier"
    foreign.write_bytes(before)
    invoked = mocker.patch.object(macos.subprocess, "run", return_value=completed())

    with pytest.raises(errors.InstallError):
        macos.install(ctx)

    assert foreign.read_bytes() == before
    invoked.assert_not_called()


@pytest.mark.parametrize("operation", ["configured_executable", "install", "uninstall"])
@pytest.mark.parametrize(
    "mismatch",
    [
        "label",
        "mode",
        "home",
        "extra-environment",
        "outside",
        "relative",
        "prefix",
        "name",
        "parent",
        "generation",
        "program",
        "session",
    ],
)
def test_unowned_carrier_is_rejected_before_any_native_mutation(
    operation, mismatch, carrier_context, tmp_path, mocker
) -> None:
    ctx = carrier_context
    carrier = Path(macos._plist_path(ctx))
    carrier.parent.mkdir(parents=True)
    payload = plistlib.loads(macos.render_plist(ctx).encode())
    if mismatch == "label":
        payload["Label"] = "unrelated.service"
    elif mismatch == "mode":
        payload["ProgramArguments"][1] = "--help"
    elif mismatch == "home":
        payload["EnvironmentVariables"]["HOME"] = str(tmp_path / "other-home")
    elif mismatch == "extra-environment":
        payload["EnvironmentVariables"]["PYTHONPATH"] = str(tmp_path / "injected")
    elif mismatch == "program":
        payload["Program"] = str(tmp_path / "foreign-executable")
    elif mismatch == "session":
        payload["LimitLoadToSessionType"] = "Aqua"
    else:
        payload["ProgramArguments"][0] = {
            "outside": str(tmp_path / "foreign/bin/codex-responses-proxy"),
            "relative": "bin/codex-responses-proxy",
            "prefix": ctx.install_dir + "-other/bin/codex-responses-proxy",
            "name": str(Path(ctx.install_dir, "bin", "other-command")),
            "parent": str(Path(ctx.install_dir, "other", "codex-responses-proxy")),
            "generation": str(
                Path(ctx.install_dir, "generations", "unverified", "bin", "codex-responses-proxy")
            ),
        }[mismatch]
    before = plistlib.dumps(payload)
    carrier.write_bytes(before)
    invoked = mocker.patch.object(macos.subprocess, "run", return_value=completed())

    with pytest.raises(errors.InstallError):
        getattr(macos, operation)(ctx)

    assert carrier.read_bytes() == before
    invoked.assert_not_called()


@pytest.mark.parametrize("operation", ["install", "uninstall"])
def test_malformed_carrier_is_preserved(carrier_context, operation, mocker) -> None:
    ctx = carrier_context
    carrier = Path(macos._plist_path(ctx))
    carrier.parent.mkdir(parents=True)
    before = b"not an owned launch-agent plist"
    carrier.write_bytes(before)
    invoked = mocker.patch.object(macos.subprocess, "run", return_value=completed())

    with pytest.raises(errors.InstallError):
        getattr(macos, operation)(ctx)

    assert carrier.read_bytes() == before
    invoked.assert_not_called()


def test_valid_legacy_generation_carrier_remains_owned(carrier_context) -> None:
    ctx = carrier_context
    carrier = Path(macos._plist_path(ctx))
    carrier.parent.mkdir(parents=True)
    payload = plistlib.loads(macos.render_plist(ctx).encode())
    payload.pop("LimitLoadToSessionType")
    executable = str(
        Path(ctx.install_dir, "generations", "a" * 32, "bin", Path(ctx.executable).name)
    )
    payload["ProgramArguments"][0] = executable
    before = plistlib.dumps(payload)
    carrier.write_bytes(before)

    assert macos.configured_executable(ctx) == executable
    assert carrier.read_bytes() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX filesystem alias identity")
def test_verified_executable_filesystem_alias_does_not_lose_ownership(
    carrier_context, tmp_path
) -> None:
    ctx = carrier_context
    install = Path(ctx.install_dir)
    install.mkdir(parents=True)
    alias = tmp_path / "same-installation"
    alias.symlink_to(install, target_is_directory=True)
    carrier = Path(macos._plist_path(ctx))
    carrier.parent.mkdir(parents=True)
    payload = plistlib.loads(macos.render_plist(ctx).encode())
    executable = str(alias / "bin" / Path(ctx.executable).name)
    payload["ProgramArguments"][0] = executable
    carrier.write_bytes(plistlib.dumps(payload))

    assert macos.configured_executable(ctx) == executable


def test_successor_carrier_uses_atomic_owned_file_io(carrier_context, mocker) -> None:
    ctx = carrier_context
    mocker.patch.object(macos, "_domain_target", return_value="user/501")
    mocker.patch.object(macos, "_service", return_value=macos._Service(True, 73))
    generation = macos.process.OwnedProcess(73, ctx.executable, 1.0)
    mocker.patch.object(macos.process, "wait_for_executable", return_value=generation)
    mocker.patch.object(macos.process, "owned_process_alive", return_value=True)
    mocker.patch.object(
        macos.subprocess,
        "run",
        side_effect=[completed(), completed(), completed(stdout="73")],
    )
    replace = mocker.spy(owned_files.os, "replace")

    macos.install(ctx)

    assert replace.call_count == 1
    assert replace.call_args.args[1] == Path(macos._plist_path(ctx))
    assert Path(macos._plist_path(ctx)).read_text(encoding="utf-8") == macos.render_plist(ctx)


def test_teardown_preserves_a_carrier_changed_after_bootout(carrier_context, mocker) -> None:
    ctx = carrier_context
    carrier = Path(macos._plist_path(ctx))
    carrier.parent.mkdir(parents=True)
    carrier.write_text(macos.render_plist(ctx), encoding="utf-8")
    mocker.patch.object(
        macos, "_registered_service", return_value=("user/501", macos._Service(True, None))
    )
    mocker.patch.object(macos, "_service", return_value=macos._Service(False, None))
    replacement = b"unowned replacement must survive"

    def bootout(*_args, **_options):
        carrier.write_bytes(replacement)
        return completed()

    invoked = mocker.patch.object(macos.subprocess, "run", side_effect=bootout)

    with pytest.raises(errors.InstallError):
        macos.uninstall(ctx)

    invoked.assert_called_once()
    assert carrier.read_bytes() == replacement
