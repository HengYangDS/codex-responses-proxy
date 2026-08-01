#!/usr/bin/env python3
"""macOS native supervision lifecycle contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.supervision import macos
from tests.supervision.fixtures import completed as _completed
from tests.supervision.fixtures import set_file as _set_file
from tests.supervision.fixtures import temporary_context as _temporary_context


class TestMacosLifecycle(unittest.TestCase):
    def test_install(self):
        with _temporary_context("home") as ctx:
            plist = macos._plist_path(ctx)
            with mock.patch.object(
                macos.subprocess,
                "run",
                side_effect=[_completed(), _completed(), _completed()],
            ) as invoked:
                macos.install(ctx)
            self.assertEqual(Path(plist).read_text(encoding="utf-8"), macos.render_plist(ctx))
            self.assertEqual(invoked.call_args_list[0].args[0], ["plutil", "-lint", plist])
            with (
                mock.patch.object(
                    macos.subprocess,
                    "run",
                    side_effect=[
                        _completed(),
                        _completed(),
                        _completed(returncode=1, stderr=" denied "),
                    ],
                ),
                self.assertRaisesRegex(errors.InstallError, "launchctl load failed: denied"),
            ):
                macos.install(ctx)

    def test_status_and_uninstall(self):
        with _temporary_context("home") as ctx:
            plist = Path(macos._plist_path(ctx))
            for exists, listing, expected in (
                (False, "", "absent"),
                (True, "other", "installed"),
                (True, runtime_context.SERVICE_ID, "running"),
            ):
                _set_file(plist, "plist" if exists else None)
                with mock.patch.object(
                    macos.subprocess, "run", return_value=_completed(stdout=listing)
                ):
                    self.assertEqual(macos.status(ctx), expected)
            for exists in (False, True):
                _set_file(plist, "plist" if exists else None)
                with mock.patch.object(
                    macos.subprocess,
                    "run",
                    side_effect=[_completed(), _completed(stdout="other")],
                ) as invoked:
                    macos.uninstall(ctx)
                self.assertFalse(plist.exists())
                self.assertEqual(invoked.call_count, 2 * int(exists))

    def test_uninstall_keeps_plist_when_launchd_removal_is_unproven(self):
        with _temporary_context("home") as ctx:
            plist = _set_file(macos._plist_path(ctx), "plist")
            with (
                mock.patch.object(
                    macos.subprocess,
                    "run",
                    return_value=_completed(returncode=1, stderr="denied"),
                ),
                self.assertRaisesRegex(errors.InstallError, "launchctl unload failed"),
            ):
                macos.uninstall(ctx)
            self.assertTrue(plist.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
