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
