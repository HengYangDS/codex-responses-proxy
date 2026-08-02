#!/usr/bin/env python3
"""Native service-definition projections for supported platforms."""

from __future__ import annotations

import sys
import unittest
import xml.dom.minidom as minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.supervision import linux, macos, windows
from tests.deployment.fixtures import platform_context
from tests.supervision.fixtures import assert_fragments as _assert_fragments

MACOS_CONTAINS = """<key>KeepAlive</key>
<true/>
/usr/bin/python3.12
codex-responses-proxy.watchdog
CODEX_RESPONSES_PROXY_PROXY_PORT
8791
CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES
4194304
CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT
CODEX_RESPONSES_PROXY_PROXY_LOG
CODEX_RESPONSES_PROXY_WATCHDOG_LOG
/home/tester/.local/state/codex-responses-proxy/watchdog.stdout.log
/home/tester/.local/state/codex-responses-proxy/watchdog.stderr.log""".splitlines()
LINUX_CONTAINS = f"""Restart=always
RestartSec=3
WantedBy=default.target
ExecStart=/usr/bin/python3.12
Environment=CODEX_RESPONSES_PROXY_PROXY_PORT=8791
Environment=CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES={runtime_config.DEFAULT_PROXY_LOG_MAX_BYTES}
Environment=CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT={runtime_config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}
Environment=CODEX_RESPONSES_PROXY_PROXY_LOG=/home/tester/.local/state/codex-responses-proxy/proxy.log
Environment=CODEX_RESPONSES_PROXY_WATCHDOG_LOG=/home/tester/.local/state/codex-responses-proxy/watchdog.log""".splitlines()
WINDOWS_TASK_CONTAINS = f"""<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
<LogonTrigger>
<RestartOnFailure>
<LogonType>InteractiveToken</LogonType>
<RunLevel>LeastPrivilege</RunLevel>
<TimeTrigger>
<StartBoundary>{windows._SELF_HEAL_START_BOUNDARY}</StartBoundary>
<Repetition>
<Interval>PT1M</Interval>
<StopAtDurationEnd>false</StopAtDurationEnd>
<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
<Command>/usr/bin/python3.12</Command>
run-watchdog.pyw""".splitlines()
WINDOWS_LAUNCHER_CONTAINS = f"""'CODEX_RESPONSES_PROXY_PROXY_PORT'] = '8801'
'CODEX_RESPONSES_PROXY_PROXY_PYTHON'] = '/usr/bin/python3.12'
'CODEX_RESPONSES_PROXY_PROXY_SCRIPT'] = '/home/tester/.local/share/codex-responses-proxy/codex_responses_proxy/listener/entrypoint.py'
'CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES'] = '{runtime_config.DEFAULT_PROXY_LOG_MAX_BYTES}'
'CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT'] = '{runtime_config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}'
'CODEX_RESPONSES_PROXY_PROXY_LOG'] = '/home/tester/.local/state/codex-responses-proxy/proxy.log'
'CODEX_RESPONSES_PROXY_WATCHDOG_LOG'] = '/home/tester/.local/state/codex-responses-proxy/watchdog.log'
runpy.run_path('/home/tester/.local/share/codex-responses-proxy/watchdog/watchdog.py', run_name='__main__')""".splitlines()


class TestServiceDefinitions(unittest.TestCase):
    def test_macos_plist(self):
        xml = macos.render_plist(platform_context())
        minidom.parseString(xml)
        _assert_fragments(
            self,
            xml,
            MACOS_CONTAINS,
            ("responses-proxy-watchdog.out.log", "responses-proxy-watchdog.err.log"),
        )

    def test_linux_unit(self):
        unit = linux.render_unit(platform_context())
        _assert_fragments(self, unit, LINUX_CONTAINS)
        self.assertNotIn("multi-user.target", unit)

    def test_windows_task(self):
        ctx = platform_context()
        xml = windows.render_task_xml(ctx)
        minidom.parseString(xml)
        _assert_fragments(self, xml, WINDOWS_TASK_CONTAINS)
        _assert_fragments(self, xml.lower(), exclude=("cmd.exe", "comspec", "run-watchdog.cmd"))

    def test_windows_launcher(self):
        ctx = platform_context(port=8801)
        launcher = windows.render_launcher(ctx)
        self.assertNotIn(
            'Arguments>"/home/tester/.local/share/codex-responses-proxy/watchdog/watchdog.py"',
            windows.render_task_xml(ctx),
        )
        _assert_fragments(self, launcher, WINDOWS_LAUNCHER_CONTAINS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
