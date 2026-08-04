"""Native service-definition projections for supported platforms."""

from __future__ import annotations

import xml.dom.minidom as minidom

from codex_responses_proxy.lifecycle.supervision import linux, macos, windows
from codex_responses_proxy.relay import config as runtime_config
from tests.lifecycle.fixtures import platform_context
from tests.lifecycle.supervision.fixtures import assert_fragments as _assert_fragments

CONTEXT = platform_context()
EXECUTABLE = CONTEXT.executable

MACOS_CONTAINS = f"""<key>KeepAlive</key>
<true/>
{EXECUTABLE}
--internal-watchdog
codex-responses-proxy.watchdog
CODEX_RESPONSES_PROXY_PROXY_PORT
8791
CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES
4194304
CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT
CODEX_RESPONSES_PROXY_PROXY_LOG
CODEX_RESPONSES_PROXY_WATCHDOG_LOG
<string>/dev/null</string>""".splitlines()
LINUX_CONTAINS = f"""Restart=always
RestartSec=3
WantedBy=default.target
ExecStart={EXECUTABLE} --internal-watchdog
Environment=CODEX_RESPONSES_PROXY_PROXY_PORT=8791
Environment=CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES={runtime_config.DEFAULT_PROXY_LOG_MAX_BYTES}
Environment=CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT={runtime_config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}
Environment=CODEX_RESPONSES_PROXY_PROXY_LOG={CONTEXT.log_dir}/proxy.log
Environment=CODEX_RESPONSES_PROXY_WATCHDOG_LOG={CONTEXT.log_dir}/watchdog.log""".splitlines()
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
<Command>{EXECUTABLE}</Command>
<Arguments>--internal-watchdog</Arguments>""".splitlines()


class TestServiceDefinitions:
    def test_macos_plist(self):
        xml = macos.render_plist(platform_context())
        minidom.parseString(xml)
        _assert_fragments(
            xml,
            MACOS_CONTAINS,
            ("responses-proxy-watchdog.out.log", "responses-proxy-watchdog.err.log"),
        )

    def test_linux_unit(self):
        unit = linux.render_unit(platform_context())
        _assert_fragments(unit, LINUX_CONTAINS)
        assert "multi-user.target" not in unit

    def test_windows_task(self):
        xml = windows.render_task_xml(platform_context())
        minidom.parseString(xml)
        _assert_fragments(xml, WINDOWS_TASK_CONTAINS)
        _assert_fragments(xml.lower(), exclude=("cmd.exe", "comspec", "run-watchdog.cmd"))

    def test_service_definitions_never_persist_python_or_source_paths(self, subtests):
        ctx = platform_context(port=8801)
        definitions = (
            macos.render_plist(ctx),
            linux.render_unit(ctx),
            windows.render_task_xml(ctx),
        )
        for definition in definitions:
            with subtests.test(definition=definition[:40]):
                assert "python" not in definition.lower()
                assert ".py" not in definition
