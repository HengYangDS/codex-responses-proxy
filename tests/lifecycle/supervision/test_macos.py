"""macOS native supervision lifecycle contracts."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle.supervision import macos
from codex_responses_proxy.runtime import config as runtime_config
from tests.lifecycle.supervision.fixtures import completed as _completed
from tests.lifecycle.supervision.fixtures import set_file as _set_file
from tests.lifecycle.supervision.fixtures import temporary_context as _temporary_context

ROOT = Path(__file__).resolve().parents[3]


def _service(pid: int) -> str:
    return f"gui/501/example = {{\n\tpid = {pid}\n}}\n"


class TestMacosLifecycle:
    @pytest.fixture(autouse=True)
    def _isolate_launch_agents(self, tmp_path, *, mocker):
        mocker.patch.object(macos.config, "home_dir", return_value=str(tmp_path))
        mocker.patch.object(
            macos.shutil,
            "which",
            side_effect=lambda name, *, path: (
                f"/native/{name}" if path == macos.os.defpath else None
            ),
        )
        mocker.patch.object(macos.os, "getuid", return_value=501, create=True)

    def test_native_tools_resolve_from_the_host_default_path(self, *, mocker) -> None:
        resolved = mocker.patch.object(
            macos.shutil,
            "which",
            side_effect=lambda name, *, path: (
                f"/native/{name}" if path == macos.os.defpath else None
            ),
        )

        assert macos._native_tool("launchctl") == "/native/launchctl"
        resolved.assert_called_once_with("launchctl", path=macos.os.defpath)

    def test_native_tool_resolution_fails_with_one_product_error(self, *, mocker) -> None:
        mocker.patch.object(macos.shutil, "which", return_value=None)

        with pytest.raises(
            errors.InstallError, match="native macOS tool is unavailable: launchctl"
        ):
            macos._native_tool("launchctl")

    def test_install_rejects_unproved_predecessor_removal(self, *, mocker) -> None:
        with _temporary_context("log_dir") as ctx:
            mocker.patch.object(macos.os, "getuid", return_value=501)
            mocker.patch.object(
                macos.process,
                "capture_executable",
                return_value=macos.process.OwnedProcess(41, ctx.executable, 1.0),
            )
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(),
                    _completed(stdout=_service(41)),
                    _completed(returncode=1, stderr=" denied "),
                ],
            )

            with pytest.raises(errors.InstallError, match="launchctl bootout failed: denied"):
                macos.install(ctx)

    def test_install_rejects_unchanged_watchdog_generation(self, *, mocker) -> None:
        with _temporary_context("log_dir") as ctx:
            mocker.patch.object(macos.os, "getuid", return_value=501)
            capture = mocker.patch.object(
                macos.process,
                "capture_executable",
            )
            generation = capture.return_value
            wait_for_exit = mocker.patch.object(macos.process, "wait_for_exit", return_value=True)
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(),
                    _completed(stdout=_service(41)),
                    _completed(),
                    _completed(),
                    _completed(stdout="41\n"),
                    _completed(stdout=_service(41)),
                ],
            )

            with pytest.raises(errors.InstallError, match="generation did not change"):
                macos.install(ctx)

            capture.assert_any_call(
                41,
                ctx.executable,
                roles={macos.service_runtime.WATCHDOG_MODE},
            )
            wait_for_exit.assert_called_once_with(generation)

    def test_install_proves_distinct_launchd_generation(self, *, mocker) -> None:
        with _temporary_context("log_dir") as ctx:
            plist = macos._plist_path(ctx)
            mocker.patch.object(macos.os, "getuid", return_value=501)
            mocker.patch.object(macos, "_native_tool", side_effect=lambda name: name)
            predecessor = macos.process.OwnedProcess(41, ctx.executable, 1.0)
            successor = macos.process.OwnedProcess(73, ctx.executable, 2.0)
            capture = mocker.patch.object(
                macos.process,
                "capture_executable",
                side_effect=[predecessor, successor],
            )
            wait_for_exit = mocker.patch.object(macos.process, "wait_for_exit", return_value=True)
            owned_process_alive = mocker.patch.object(
                macos.process, "owned_process_alive", return_value=True
            )
            invoked = mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(),
                    _completed(stdout=_service(41)),
                    _completed(),
                    _completed(),
                    _completed(stdout="73\n"),
                    _completed(stdout=_service(73)),
                ],
            )

            macos.install(ctx)

            assert Path(ctx.log_dir).is_dir()
            assert Path(plist).read_text(encoding="utf-8") == macos.render_plist(ctx)
            assert [call.args[0] for call in invoked.call_args_list] == [
                ["plutil", "-lint", plist],
                ["launchctl", "print", f"gui/501/{ctx.service_id}"],
                ["launchctl", "bootout", f"gui/501/{ctx.service_id}"],
                ["launchctl", "bootstrap", "gui/501", plist],
                ["launchctl", "kickstart", "-p", f"gui/501/{ctx.service_id}"],
                ["launchctl", "print", f"gui/501/{ctx.service_id}"],
            ]
            assert capture.call_args_list == [
                mocker.call(
                    41,
                    ctx.executable,
                    roles={macos.service_runtime.WATCHDOG_MODE},
                ),
                mocker.call(
                    73,
                    ctx.executable,
                    roles={macos.service_runtime.WATCHDOG_MODE},
                ),
            ]
            wait_for_exit.assert_called_once_with(predecessor)
            owned_process_alive.assert_called_once_with(successor)

    def test_install_rejects_bootstrap_failure(self, *, mocker) -> None:
        with _temporary_context("log_dir") as ctx:
            mocker.patch.object(macos.os, "getuid", return_value=501)
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(),
                    _completed(returncode=113),
                    _completed(returncode=1, stderr=" denied "),
                ],
            )

            with pytest.raises(errors.InstallError, match="launchctl bootstrap failed: denied"):
                macos.install(ctx)

    def test_plist_executes_the_installed_binary_in_private_watchdog_mode(self):
        with _temporary_context("log_dir") as ctx:
            rendered = macos.render_plist(ctx)
        assert f"<string>{ctx.executable}</string>" in rendered
        assert "<string>--internal-watchdog</string>" in rendered
        assert "python" not in rendered.lower()
        assert ".py" not in rendered

    def test_plist_serialization_preserves_special_characters(self):
        with _temporary_context("log_dir") as ctx:
            ctx.executable = f"{ctx.executable} & native"
            payload = plistlib.loads(macos.render_plist(ctx).encode())

        assert payload["ProgramArguments"] == [
            ctx.executable,
            macos.service_runtime.WATCHDOG_MODE,
        ]

    def test_configured_executable_reads_only_a_valid_watchdog_plist(self):
        with _temporary_context("log_dir") as ctx:
            plist = Path(macos._plist_path(ctx))
            assert macos.configured_executable(ctx) is None
            _set_file(plist, macos.render_plist(ctx))
            assert macos.configured_executable(ctx) == ctx.executable
            _set_file(plist, "not a plist")
            assert macos.configured_executable(ctx) is None

    def test_rendered_plist_captures_watchdog_stderr(self):
        with _temporary_context("log_dir") as ctx:
            rendered = macos.render_plist(ctx)
        assert "<key>StandardErrorPath</key>\n  <string>/dev/null</string>" not in rendered
        stderr_log = runtime_config.path_join(ctx.log_dir, "watchdog.stderr.log")
        assert f"<string>{stderr_log}</string>" in rendered

    def test_status_and_uninstall(self, *, mocker):
        with _temporary_context("log_dir") as ctx:
            plist = Path(macos._plist_path(ctx))
            for exists, result, expected in (
                (False, _completed(returncode=113), "absent"),
                (True, _completed(returncode=113), "installed"),
                (True, _completed(stdout=_service(73)), "running"),
            ):
                _set_file(plist, "plist" if exists else None)
                mocker.patch.object(macos.subprocess, "run", return_value=result)
                assert macos.status(ctx) == expected
            for exists in (False, True):
                _set_file(plist, "plist" if exists else None)
                invoked = mocker.patch.object(
                    macos.subprocess,
                    "run",
                    side_effect=[
                        _completed(returncode=113),
                        _completed(returncode=113),
                    ],
                )
                macos.uninstall(ctx)
                assert not plist.exists()
                assert invoked.call_count == 2

    def test_uninstall_keeps_plist_when_launchd_removal_is_unproven(self, *, mocker):
        with _temporary_context("log_dir") as ctx:
            plist = _set_file(macos._plist_path(ctx), "plist")
            mocker.patch.object(
                macos.process,
                "capture_executable",
                return_value=macos.process.OwnedProcess(73, ctx.executable, 1.0),
            )
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(stdout=_service(73)),
                    _completed(returncode=1, stderr="denied"),
                ],
            )
            with pytest.raises(errors.InstallError, match="launchctl bootout failed"):
                macos.uninstall(ctx)
            assert plist.exists()

    def test_uninstall_boots_out_registered_service_when_plist_is_missing(self, *, mocker):
        with _temporary_context("log_dir") as ctx:
            plist = Path(macos._plist_path(ctx))
            plist.unlink(missing_ok=True)
            mocker.patch.object(macos.os, "getuid", return_value=501)
            mocker.patch.object(macos, "_native_tool", side_effect=lambda name: name)
            invoked = mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(stdout="registered without a running pid"),
                    _completed(),
                    _completed(returncode=113),
                ],
            )

            macos.uninstall(ctx)

            assert [call.args[0] for call in invoked.call_args_list] == [
                ["launchctl", "print", f"gui/501/{ctx.service_id}"],
                ["launchctl", "bootout", f"gui/501/{ctx.service_id}"],
                ["launchctl", "print", f"gui/501/{ctx.service_id}"],
            ]

    def test_uninstall_keeps_plist_when_launchd_remains_registered(self, *, mocker) -> None:
        with _temporary_context("log_dir") as ctx:
            plist = _set_file(macos._plist_path(ctx), "plist")
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(stdout="registered without a running pid"),
                    _completed(),
                    _completed(stdout=_service(73)),
                ],
            )
            with pytest.raises(errors.InstallError, match="remains registered"):
                macos.uninstall(ctx)
            assert plist.exists()
