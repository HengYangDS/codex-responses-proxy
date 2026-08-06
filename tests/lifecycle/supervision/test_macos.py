"""macOS native supervision lifecycle contracts."""

from __future__ import annotations

from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import macos
from codex_responses_proxy.runtime import config as runtime_config
from tests.lifecycle.supervision.fixtures import completed as _completed
from tests.lifecycle.supervision.fixtures import set_file as _set_file
from tests.lifecycle.supervision.fixtures import temporary_context as _temporary_context
import pytest

ROOT = Path(__file__).resolve().parents[3]


class TestMacosLifecycle:
    def test_install(self, *, mocker):
        with _temporary_context("home") as ctx:
            ctx.log_dir = str(Path(ctx.home) / "state")
            plist = macos._plist_path(ctx)
            invoked = mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[_completed(), _completed(), _completed()],
            )
            macos.install(ctx)
            assert Path(ctx.log_dir).is_dir()
            assert Path(plist).read_text(encoding="utf-8") == macos.render_plist(ctx)
            assert invoked.call_args_list[0].args[0] == ["plutil", "-lint", plist]
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[
                    _completed(),
                    _completed(),
                    _completed(returncode=1, stderr=" denied "),
                ],
            )
            with pytest.raises(errors.InstallError, match="launchctl load failed: denied"):
                macos.install(ctx)

    def test_plist_executes_the_installed_binary_in_private_watchdog_mode(self):
        with _temporary_context("home") as ctx:
            rendered = macos.render_plist(ctx)
        assert f"<string>{ctx.executable}</string>" in rendered
        assert "<string>--internal-watchdog</string>" in rendered
        assert "python" not in rendered.lower()
        assert ".py" not in rendered

    def test_rendered_plist_captures_watchdog_stderr(self):
        with _temporary_context("home") as ctx:
            ctx.log_dir = str(Path(ctx.home) / "state")
            rendered = macos.render_plist(ctx)
        assert "<key>StandardErrorPath</key>\n  <string>/dev/null</string>" not in rendered
        stderr_log = runtime_config.path_join(ctx.log_dir, "watchdog.stderr.log")
        assert f"<string>{stderr_log}</string>" in rendered

    def test_status_and_uninstall(self, *, mocker):
        with _temporary_context("home") as ctx:
            plist = Path(macos._plist_path(ctx))
            for exists, listing, expected in (
                (False, "", "absent"),
                (True, "other", "installed"),
                (True, runtime_context.SERVICE_ID, "running"),
            ):
                _set_file(plist, "plist" if exists else None)
                mocker.patch.object(
                    macos.subprocess, "run", return_value=_completed(stdout=listing)
                )
                assert macos.status(ctx) == expected
            for exists in (False, True):
                _set_file(plist, "plist" if exists else None)
                invoked = mocker.patch.object(
                    macos.subprocess,
                    "run",
                    side_effect=[_completed(), _completed(stdout="other")],
                )
                macos.uninstall(ctx)
                assert not plist.exists()
                assert invoked.call_count == 2 * int(exists)

    def test_uninstall_keeps_plist_when_launchd_removal_is_unproven(self, *, mocker):
        with _temporary_context("home") as ctx:
            plist = _set_file(macos._plist_path(ctx), "plist")
            mocker.patch.object(
                macos.subprocess,
                "run",
                return_value=_completed(returncode=1, stderr="denied"),
            )
            with pytest.raises(errors.InstallError, match="launchctl unload failed"):
                macos.uninstall(ctx)
            assert plist.exists()

    def test_uninstall_keeps_plist_when_launchd_remains_registered(self, *, mocker) -> None:
        with _temporary_context("home") as ctx:
            plist = _set_file(macos._plist_path(ctx), "plist")
            mocker.patch.object(
                macos.subprocess,
                "run",
                side_effect=[_completed(), _completed(stdout=runtime_context.SERVICE_ID)],
            )
            with pytest.raises(errors.InstallError, match="remains registered"):
                macos.uninstall(ctx)
            assert plist.exists()
