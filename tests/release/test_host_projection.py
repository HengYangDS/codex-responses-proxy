"""Native acceptance conserves user and GUI launchd surfaces separately."""

from __future__ import annotations

import pytest

from tests.lifecycle.supervision.fixtures import completed
from tests.release import fixtures


@pytest.mark.parametrize("gui", [False, True])
def test_macos_projection_observes_only_proved_domains(gui, tmp_path, mocker) -> None:
    mocker.patch.object(fixtures.os, "getuid", return_value=501, create=True)
    mocker.patch.object(fixtures.Path, "home", return_value=tmp_path)
    product = fixtures.runtime_context.SERVICE_ID
    login = "\tgui asid = 42\n" if gui else ""
    domain = f"user/501 = {{\n\ttype = user\n{login}\tservices = {{\n\t\t73 0 {product}\n\t}}\n}}\n"
    inputs = {
        ("print", "user/501"): domain,
        ("print-disabled", "user/501"): f'disabled services = {{\n "{product}" => enabled\n}}',
        (
            "print",
            "gui/501",
        ): f"gui/501 = {{\n\tservices = {{\n\t\t42 0 {product}.012345abcdef\n\t}}\n}}\n",
        (
            "print-disabled",
            "gui/501",
        ): f'disabled services = {{\n "{product}.012345abcdef" => disabled\n}}',
    }

    def invoke(arguments, **_options):
        if arguments[1] == "list":
            return completed(stdout=f"PID\tStatus\tLabel\n73\t0\t{product}\n")
        return completed(stdout=inputs[tuple(arguments[1:])])

    invoked = mocker.patch.object(fixtures.subprocess, "run", side_effect=invoke)
    labels, overrides, plists = fixtures._macos_service_projection()

    assert ("user/501", product) in labels
    assert ("user/501", product, "enabled") in overrides
    assert (("gui/501", product + ".012345abcdef") in labels) is gui
    assert (("gui/501", product + ".012345abcdef", "disabled") in overrides) is gui
    assert plists == ()
    assert not any(call.args[0][1] == "list" for call in invoked.call_args_list)


def test_macos_projection_preserves_observation_failure(tmp_path, mocker) -> None:
    mocker.patch.object(fixtures.os, "getuid", return_value=501, create=True)
    mocker.patch.object(fixtures.Path, "home", return_value=tmp_path)
    invoked = mocker.patch.object(
        fixtures.subprocess, "run", return_value=completed(returncode=125)
    )
    with pytest.raises(RuntimeError, match="user-domain observation failed"):
        fixtures._macos_service_projection()
    assert [call.args[0] for call in invoked.call_args_list] == [
        ["/bin/launchctl", "print", "user/501"]
    ]


@pytest.mark.parametrize("changed", [None, "provider", "receipt", "extra", "runtime"])
def test_authentic_payload_identity_rejects_partial_or_substituted_state(
    changed, tmp_path, mocker
) -> None:
    from codex_responses_proxy.lifecycle import generation
    from codex_responses_proxy.lifecycle import projection
    from codex_responses_proxy.service import inventory
    from tests.lifecycle.fixtures import install_context
    from tests.lifecycle.fixtures import install_payload
    from tests.lifecycle.fixtures import released_artifact

    ctx = install_context(tmp_path)
    install_payload(ctx, mocker=mocker)
    admitted = released_artifact()
    selected = generation.selected_context(ctx)
    runtime = {
        "pid": 321,
        "release": admitted.version,
        "release_receipt_sha256": admitted.receipt_sha256,
        "serving_payload_sha256": admitted.serving_payload_sha256,
        "accepting": True,
        "draining": False,
    }
    observed = {"state": "running", "release": admitted.version, "runtime": runtime}
    if changed == "provider":
        (fixtures.Path(selected.payload_dir) / inventory.PROVIDER_MANIFEST).write_bytes(b"changed")
    elif changed == "receipt":
        (fixtures.Path(selected.payload_dir) / inventory.RELEASE_RECEIPT_FILENAME).write_bytes(
            b"{}"
        )
    elif changed == "extra":
        (fixtures.Path(selected.payload_dir) / "unadmitted-file").write_bytes(b"unowned")
    elif changed == "runtime":
        runtime["release_receipt_sha256"] = "0" * 64
    assert projection.payload_manifest_path(selected).is_file()

    if changed is None:
        fixtures.assert_admitted_payload_identity(ctx, admitted, observed)
    else:
        with pytest.raises(AssertionError):
            fixtures.assert_admitted_payload_identity(ctx, admitted, observed)


@pytest.mark.parametrize("exit_race", [False, True])
def test_old_controller_interruption_awaits_child_before_parent(
    exit_race, tmp_path, mocker
) -> None:
    executable = tmp_path / "old-controller"
    parent = fixtures.process.OwnedProcess(201, str(executable), 1.0)
    child = fixtures.process.OwnedProcess(202, str(executable), 2.0)
    controller = mocker.Mock(pid=parent.pid)
    events = []
    mocker.patch.object(fixtures.process, "pids_naming_executable", return_value=[])
    mocker.patch.object(
        fixtures.process,
        "capture_executable",
        side_effect=lambda pid, *_args, **_kwargs: {201: parent, 202: child}[pid],
    )
    mocker.patch.object(fixtures.process, "owned_process_alive", return_value=True)

    def native_process(pid):
        if exit_race and pid == child.pid:
            raise fixtures.psutil.NoSuchProcess(pid)
        native = mocker.Mock()
        native.create_time.return_value = {201: 1.0, 202: 2.0}[pid]
        native.kill.side_effect = lambda: events.append(("kill", pid))
        return native

    mocker.patch.object(fixtures.psutil, "Process", side_effect=native_process)
    mocker.patch.object(
        fixtures.process,
        "wait_for_exit",
        side_effect=lambda owned, **_: events.append(("wait", owned.pid)) or True,
    )
    fixtures.interrupt_native_controller(controller, executable, (parent, child))
    assert events == ([("kill", 201)] if exit_race else [("kill", 202), ("kill", 201)]) + [
        ("wait", 202),
        ("wait", 201),
    ]
    controller.wait.assert_called_once_with(timeout=30)


@pytest.mark.parametrize("residue", [None, "service", "listener", "process", "command"])
def test_public_native_cleanup_cannot_hide_residue(residue, tmp_path, mocker) -> None:
    from tests.lifecycle.fixtures import install_context

    ctx = install_context(tmp_path)
    service = mocker.Mock()
    service.status.return_value = "running" if residue == "service" else "absent"
    service.configured_executable.return_value = None
    mocker.patch.object(fixtures.native_service, "adapter", return_value=service)
    mocker.patch.object(
        fixtures.process, "listener_pids", return_value=[321] if residue == "listener" else []
    )
    mocker.patch.object(
        fixtures.process,
        "pids_naming_executable",
        return_value=[321] if residue == "process" else [],
    )
    if residue == "command":
        mocker.patch.object(fixtures.Path, "exists", return_value=False)
        mocker.patch.object(fixtures.Path, "is_symlink", return_value=True)
    if residue is None:
        fixtures.assert_native_target_absent(ctx, (ctx,))
    else:
        with pytest.raises(AssertionError):
            fixtures.assert_native_target_absent(ctx, (ctx,))
