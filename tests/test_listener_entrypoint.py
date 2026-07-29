#!/usr/bin/env python3
"""Executable listener bootstrap contracts."""

from __future__ import annotations

import runpy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "codex_dmx_proxy" / "listener" / "entrypoint.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.listener import entrypoint


class TestListenerEntrypoint(unittest.TestCase):
    def test_script_bootstrap_runs_main(self) -> None:
        namespace = runpy.run_path(str(ENTRYPOINT), run_name="listener_bootstrap_test")
        self.assertEqual(namespace["ROOT"], ROOT)
        self.assertTrue(callable(namespace["main"]))

    def test_main_delegates_handoff_child(self) -> None:
        context = mock.sentinel.handoff_context
        with (
            mock.patch.object(entrypoint, "configure_http_surface") as configure,
            mock.patch.object(entrypoint, "_handoff_context", return_value=context),
            mock.patch.object(entrypoint.handoff, "run_child", return_value=7) as run_child,
            mock.patch.object(entrypoint.sys, "argv", ["entrypoint.py", "--handoff-child"]),
            self.assertRaisesRegex(SystemExit, "7"),
        ):
            entrypoint.main()
        configure.assert_called_once_with()
        run_child.assert_called_once_with(context)

    def test_main_closes_normal_server_after_keyboard_interrupt(self) -> None:
        listener = mock.Mock()
        context = mock.sentinel.handoff_context
        with (
            mock.patch.dict(entrypoint.os.environ, {}, clear=True),
            mock.patch.object(entrypoint, "configure_http_surface") as configure,
            mock.patch.object(entrypoint, "create_server", return_value=listener),
            mock.patch.object(entrypoint, "_handoff_context", return_value=context),
            mock.patch.object(entrypoint.state, "log") as log,
            mock.patch.object(
                entrypoint.handoff,
                "serve_with_resume",
                side_effect=KeyboardInterrupt,
            ) as serve,
            mock.patch.object(entrypoint.sys, "argv", ["entrypoint.py"]),
        ):
            entrypoint.main()
        configure.assert_called_once_with()
        log.assert_called_once()
        serve.assert_called_once_with(listener, context)
        listener.server_close.assert_called_once_with()
        self.assertIs(entrypoint._SERVER_INSTANCE, listener)


if __name__ == "__main__":
    unittest.main(verbosity=2)
