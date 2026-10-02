"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import override

import pytest
import yaml

from tests.quality.fixtures import ROOT
from tools.ci import project
from tools.quality import governance
from tools.quality import python_matrix


@pytest.fixture
def peer_link_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Own exact publication roots without relying on any operator network."""
    root = tmp_path / "link scope"
    (root / ".ethos").mkdir(parents=True)
    (root / ".ethos/release.toml").write_text(
        '[[publication.peers]]\nid = "forge-a"\n'
        'forge_repository = "https://a.example.test/team/project"\n\n'
        '[[publication.peers]]\nid = "forge-b"\n'
        'forge_repository = "http://b.example.test:8080/group/project+one"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(governance, "ROOT", root)
    monkeypatch.setattr(governance, "_tracked_current", lambda _suffixes: ("README.md",))
    return root


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("peer", ["forge-a", "forge-b"])
def test_online_link_scope_excludes_only_the_other_exact_declared_repository(
    peer_link_project: Path, peer: str
) -> None:
    command = next(
        command
        for command in governance._commands(online_links=True, peer=peer)
        if command[0] == "lychee"
    )
    exclusions = [
        item.removeprefix("--exclude=") for item in command if item.startswith("--exclude=")
    ]
    assert len(exclusions) == 1
    peers = tomllib.loads((peer_link_project / ".ethos/release.toml").read_text())["publication"][
        "peers"
    ]
    selected = next(record["forge_repository"] for record in peers if record["id"] == peer)
    other = next(record["forge_repository"] for record in peers if record["id"] != peer)
    expression = re.compile(exclusions[0])
    for suffix in ("", "/compare/v1.0.0...main", "?view=history", "#releases"):
        assert expression.search(other + suffix)
        assert not expression.search(selected + suffix)
    assert not expression.search(other + "-different/compare/v1.0.0...main")
    assert not expression.search(other.replace("project", "another-project"))
    assert not expression.search("https://upstream.example.test/reference")
    assert not expression.search("file:///local/source.md")
    assert "--offline" not in command
    assert "--accept-timeouts" not in command
    assert "--exclude-private" not in command
    assert "--insecure" not in command


@pytest.mark.parametrize("peer", ["", "undeclared"])
def test_online_link_scope_rejects_an_undeclared_peer(peer_link_project: Path, peer: str) -> None:
    assert (peer_link_project / ".ethos/release.toml").is_file()
    with pytest.raises(governance.GovernanceError, match="declared publication peer"):
        governance._commands(online_links=True, peer=peer)


def test_offline_verification_has_no_peer_dependency(peer_link_project: Path) -> None:
    (peer_link_project / ".ethos/release.toml").unlink()
    for online in (False, True):
        command = next(
            command
            for command in governance._commands(online_links=online)
            if command[0] == "lychee"
        )
        assert not any(item.startswith("--exclude") for item in command)
        assert ("--offline" in command) is (not online)
    with pytest.raises(governance.GovernanceError, match="requires --online-links"):
        governance._commands(online_links=False, peer="forge-a")


@pytest.mark.repository_toolchain
@pytest.mark.parametrize(
    "repository",
    [
        "ftp://b.example.test/group/project",
        "https://b.example.test",
        "https://b.example.test/",
        "https://b.example.test/group/project?secret=input",
        "https://b.example.test/group/project#history",
        "https://user@b.example.test/group/project",
        "https://b.example.test:invalid/group/project",
        "https://b.example.test:0/group/project",
        "https://b.example.test:65536/group/project",
        "https://b.example.test/group/project?",
        "https://b.example.test/group/project#",
        "https://@b.example.test/group/project",
        "https:///@b.example.test/group/project",
        "https://\\@b.example.test/group/project",
        "https://user:password@b.example.test/group/project",
        "https://b.example.test/project/..",
        "https://[v1.foo]/group/project",
        "not-a-url",
    ],
)
def test_online_link_scope_cannot_hide_a_malformed_repository_identity(
    peer_link_project: Path, repository: str
) -> None:
    metadata = peer_link_project / ".ethos/release.toml"
    metadata.write_text(
        metadata.read_text().replace(
            '"http://b.example.test:8080/group/project+one"', json.dumps(repository)
        ),
        encoding="utf-8",
    )
    with pytest.raises(governance.GovernanceError, match="publication peer identity"):
        governance._commands(online_links=True, peer="forge-a")


@pytest.mark.parametrize(
    "source",
    [
        "",
        "[publication]\npeers = []\n",
        "[publication]\npeers = 1\n",
        "[publication]\npeers = [1]\n",
        '[[publication.peers]]\nid = ""\nforge_repository = "https://a.test/project"\n',
        '[[publication.peers]]\nid = 1\nforge_repository = "https://a.test/project"\n',
        '[[publication.peers]]\nid = "forge a"\nforge_repository = "https://a.test/project"\n',
        '[[publication.peers]]\nid = "forge-a"\nforge_repository = 1\n',
        '[[publication.peers]]\nid = "forge-a"\n',
        '[[publication.peers]]\nid = "forge-a"\nforge_repository = "https://a.test/bad path"\n',
        '[[publication.peers]]\nid = "forge-a"\nforge_repository = "https://a.test/project"\n'
        '[[publication.peers]]\nid = "forge-a"\nforge_repository = "https://b.test/project"\n',
        pytest.param(
            '[[publication.peers]]\nid = "forge-a"\nforge_repository = "https://a.test/project/"\n'
            '[[publication.peers]]\nid = "forge-b"\nforge_repository = "https://a.test/project"\n',
            marks=pytest.mark.repository_toolchain,
        ),
        pytest.param(
            '[[publication.peers]]\nid = "forge-a"\n'
            'forge_repository = "https://a.test/group/project/nested"\n'
            '[[publication.peers]]\nid = "forge-b"\n'
            'forge_repository = "https://a.test/group/project"\n',
            marks=pytest.mark.repository_toolchain,
        ),
    ],
)
def test_peer_link_scope_rejects_ambiguous_or_incomplete_native_declarations(
    peer_link_project: Path, source: str
) -> None:
    (peer_link_project / ".ethos/release.toml").write_text(source, encoding="utf-8")
    with pytest.raises(governance.GovernanceError, match="publication peer identity"):
        governance._commands(online_links=True, peer="forge-a")


def test_peer_link_scope_missing_authority_never_becomes_an_empty_filter(
    peer_link_project: Path,
) -> None:
    (peer_link_project / ".ethos/release.toml").unlink()
    with pytest.raises(governance.GovernanceError, match="publication peer identity"):
        governance._commands(online_links=True, peer="forge-a")


@pytest.mark.repository_toolchain
@pytest.mark.parametrize(
    ("selected", "other"),
    [
        ("https://SAME.example/team/project", "https://same.example/team/project"),
        ("https://same.example:443/team/project", "https://same.example/team/project"),
        ("http://same.example:80/team/project", "http://same.example/team/project"),
        ("https://SAME.example/team/project/nested", "https://same.example:443/team/project"),
        ("http://[0:0:0:0:0:0:0:1]/team/project", "http://[::1]/team/project"),
        ("https://[2001:DB8:0:0:0:0:0:1]/team/project", "https://[2001:db8::1]:443/team/project"),
        ("https://%73ame.example/team/project", "https://same.example/team/project"),
        ("http://127.1/team/project", "http://127.0.0.1/team/project"),
        ("http://2130706433/team/project", "http://127.0.0.1/team/project"),
        ("http://0x7f000001/team/project", "http://127.0.0.1/team/project"),
        ("http://0177.0.0.1/team/project", "http://127.0.0.1/team/project"),
        ("https://faß.example/team/project", "https://xn--fa-hia.example/team/project"),
        ("https://same.example/a/../team/project", "https://same.example/team/project"),
        ("https://same.example/team/%2e%2e/team/project", "https://same.example/team/project"),
        ("https://same.example/team\\project", "https://same.example/team/project"),
        ("https://same.example/team/é", "https://same.example/team/%C3%A9"),
        ("https://same.example/team/project", "https://same.example/team/project/nested"),
    ],
)
def test_peer_link_scope_cannot_exclude_a_normalized_selected_repository(
    peer_link_project: Path, selected: str, other: str
) -> None:
    (peer_link_project / ".ethos/release.toml").write_text(
        f'[[publication.peers]]\nid = "forge-a"\nforge_repository = {json.dumps(selected)}\n'
        f'[[publication.peers]]\nid = "forge-b"\nforge_repository = {json.dumps(other)}\n',
        encoding="utf-8",
    )
    with pytest.raises(governance.GovernanceError, match="publication peer identity"):
        governance._commands(online_links=True, peer="forge-a")


def test_peer_link_scope_cli_rejects_unknown_selection_without_running_tools(
    peer_link_project: Path, capsys: pytest.CaptureFixture[str], mocker
) -> None:
    assert (peer_link_project / ".ethos/release.toml").is_file()
    tools = mocker.patch.object(governance.subprocess, "run")
    with pytest.raises(SystemExit) as failure:
        governance.main(("--online-links", "--peer", "undeclared"))
    assert failure.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "declared publication peer" in output.err
    assert "Traceback" not in output.err
    tools.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        OSError("native parser unavailable"),
        subprocess.CalledProcessError(1, ("node",)),
        subprocess.TimeoutExpired(("node",), 10),
        UnicodeError("native output unavailable"),
    ],
)
def test_peer_link_scope_failed_native_observation_never_creates_an_exclusion(
    peer_link_project: Path, failure: Exception, capsys: pytest.CaptureFixture[str], mocker
) -> None:
    assert (peer_link_project / ".ethos/release.toml").is_file()
    tools = mocker.patch.object(governance.subprocess, "run", side_effect=failure)
    with pytest.raises(SystemExit) as rejected:
        governance.main(("--online-links", "--peer", "forge-a"))
    assert rejected.value.code == 1
    tools.assert_called_once()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "publication peer identity is invalid\n"


@pytest.mark.parametrize("output", ["not-json", "{}", "[]", '["https://a.test/project"]', "[1, 2]"])
def test_peer_link_scope_invalid_native_output_never_creates_an_exclusion(
    peer_link_project: Path, output: str, mocker
) -> None:
    assert (peer_link_project / ".ethos/release.toml").is_file()
    native = mocker.patch.object(
        governance.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(("node",), 0, stdout=output),
    )
    with pytest.raises(governance.GovernanceError, match="publication peer identity"):
        governance._commands(online_links=True, peer="forge-a")
    native.assert_called_once()


def test_peer_link_parser_uses_bounded_utf8_stdin_not_declaration_arguments(mocker) -> None:
    declarations = {"forge-a": "https://input-only.example.test/group/project"}
    native = mocker.patch.object(
        governance.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            ("node",), 0, stdout=json.dumps(list(declarations.values()))
        ),
    )
    assert governance._canonical_repository_roots(declarations) == declarations
    native.assert_called_once()
    invocation = native.call_args
    assert invocation.args[0][:3] == ("node", "--input-type=module", "--eval")
    assert all(
        value not in argument for value in declarations.values() for argument in invocation.args[0]
    )
    assert json.loads(invocation.kwargs["input"]) == list(declarations.values())
    assert invocation.kwargs["cwd"] == governance.ROOT
    assert invocation.kwargs["encoding"] == "utf-8"
    assert invocation.kwargs["capture_output"] is True
    assert invocation.kwargs["check"] is True
    assert 0 < invocation.kwargs["timeout"] <= 10


@pytest.mark.parametrize("peer", ["forge-a", "forge-b"])
def test_peer_link_scope_builds_only_exact_exclusions_from_native_observation(
    peer_link_project: Path, peer: str, capsys: pytest.CaptureFixture[str], mocker
) -> None:
    declarations = tomllib.loads((peer_link_project / ".ethos/release.toml").read_text())[
        "publication"
    ]["peers"]
    roots = [record["forge_repository"] for record in declarations]
    native = mocker.patch.object(
        governance.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(("node",), 0, stdout=json.dumps(roots)),
    )
    other = next(record["forge_repository"] for record in declarations if record["id"] != peer)
    assert governance._peer_link_exclusions(peer) == (f"--exclude=^{re.escape(other)}(?:[/?#]|$)",)
    native.assert_called_once()
    mocker.patch.object(governance, "_commands", return_value=())
    governance.audit(online_links=True, peer=peer)
    assert capsys.readouterr().out == (
        f"Online links: selected peer {peer}; other declared repositories are network-unqualified.\n"
    )
    native.assert_called_once()


@pytest.mark.parametrize(
    "roots",
    [
        ["https://a.test/project", "https://a.test/project"],
        ["https://a.test/project/nested", "https://a.test/project"],
        ["https://a.test/project", "https://a.test/project/nested"],
    ],
)
def test_peer_link_scope_refuses_overlap_in_native_observation(
    peer_link_project: Path, roots: list[str], mocker
) -> None:
    assert (peer_link_project / ".ethos/release.toml").is_file()
    native = mocker.patch.object(
        governance.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(("node",), 0, stdout=json.dumps(roots)),
    )
    with pytest.raises(governance.GovernanceError, match="overlapping repositories"):
        governance._peer_link_exclusions("forge-a")
    native.assert_called_once()


@pytest.mark.repository_toolchain
def test_peer_link_cli_does_not_expose_rejected_credential_input(
    peer_link_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = peer_link_project / ".ethos/release.toml"
    metadata.write_text(
        metadata.read_text().replace(
            "http://b.example.test:8080/group/project+one",
            "https://canary:synthetic-input@b.example.test/group/project",
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as rejected:
        governance.main(("--online-links", "--peer", "forge-a"))
    assert rejected.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "publication peer identity is invalid\n"
    assert "canary" not in output.err
    assert "synthetic-input" not in output.err


@pytest.mark.repository_toolchain
def test_native_peer_link_scope_preserves_success_and_bad_link_refusal(
    peer_link_project: Path,
) -> None:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            self.send_response(200 if self.path == "/selected/page" else 404)
            self.end_headers()

        @override
        def log_message(self, *_args: object, **_kwargs: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        (peer_link_project / ".ethos/release.toml").write_text(
            '[[publication.peers]]\nid = "forge-a"\n'
            f'forge_repository = "{origin}/selected"\n\n'
            '[[publication.peers]]\nid = "forge-b"\n'
            f'forge_repository = "{origin}/unselected"\n',
            encoding="utf-8",
        )
        command = next(
            command
            for command in governance._commands(online_links=True, peer="forge-a")
            if command[0] == "lychee"
        )
        exclusions = tuple(item for item in command if item.startswith("--exclude="))
        document = peer_link_project / "README.md"
        cases = (("/selected/page", 0), ("/selected/missing", 2), ("/unselected-other/missing", 2))
        for suffix, expected in cases:
            requests.clear()
            document.write_text(
                f"[Selected]({origin}{suffix})\n\n[Other peer]({origin}/unselected/missing)\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                (
                    "mise",
                    "exec",
                    "--locked",
                    "--",
                    "lychee",
                    "--config",
                    str(ROOT / ".config/quality/native/lychee.toml"),
                    "--max-retries",
                    "0",
                    "--timeout",
                    "2",
                    "--no-progress",
                    "--require-https=false",
                    *exclusions,
                    "--",
                    str(document),
                ),
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            assert result.returncode == expected, result.stdout + result.stderr
            assert suffix in requests
            assert "/unselected/missing" not in requests
            if expected:
                assert "404" in result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive()


@pytest.mark.parametrize("failed", [None, "governance", "quality"])
def test_full_verification_stops_before_failed_prerequisite_dependents(
    failed: str | None, tmp_path: Path
) -> None:
    fixture = tmp_path / "noxfile.py"
    marker = tmp_path / "observed.log"
    fixture.write_text(
        "import pathlib, runpy, nox, nox.registry\n"
        f"runpy.run_path({str(ROOT / 'noxfile.py')!r})\n"
        "nox.options.default_venv_backend = 'none'\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "def observe(session):\n"
        "    with marker.open('a') as stream:\n"
        "        stream.write(session.name + '\\n')\n"
        f"    if session.name == {failed!r}:\n"
        "        session.error('required prerequisite failed')\n"
        "for name in ('governance', 'quality'):\n"
        "    registered = nox.registry.get()[name]\n"
        "    registered.func = observe\n"
        "    registered.venv_backend = 'none'\n"
        "for version in ('3.13', '3.14'):\n"
        "    nox.session(python=False, name='tests-' + version)(observe)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "nox", "-f", str(fixture), "-s", "full"],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert (completed.returncode == 0) is (failed is None), completed.stderr
    expected = (
        ["governance"]
        if failed == "governance"
        else ["governance", "quality"]
        if failed == "quality"
        else ["governance", "quality", "tests-3.13", "tests-3.14"]
    )
    assert marker.read_text().splitlines() == expected


@pytest.mark.parametrize("explicit", [False, True])
def test_matrix_cli_projects_to_exact_selected_output(explicit, tmp_path, monkeypatch):
    output = tmp_path / "output"
    args = (
        "--versions",
        str(ROOT / ".python-versions"),
        "--release",
        str(ROOT / ".python-release"),
        "--metadata",
        str(ROOT / "pyproject.toml"),
    )
    if explicit:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        python_matrix.main((*args, "--output", str(output)))
    else:
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        python_matrix.main(args)
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert json.loads(values["value"]) == (ROOT / ".python-versions").read_text().splitlines()
    assert values["release"] == (ROOT / ".python-release").read_text().strip()


def test_matrix_cli_requires_an_output_and_nonempty_unique_versions(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    with pytest.raises(SystemExit, match="output path is unavailable"):
        python_matrix.main(())
    versions = tmp_path / "versions"
    versions.write_text("")
    with pytest.raises(ValueError, match="matrix is unavailable"):
        python_matrix.write(
            versions=versions,
            release=ROOT / ".python-release",
            metadata=ROOT / "pyproject.toml",
            output=tmp_path / "output",
        )


def _load_yaml(path: Path) -> dict[str, object]:
    """Load a workflow as semantic data rather than presentation text."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert all(isinstance(key, str) for key in data)
    return {str(key): value for key, value in data.items()}


def _mapping(value: object) -> dict[str, object]:
    """Narrow one parsed configuration table for semantic assertions."""
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return {str(key): item for key, item in value.items()}


def _required_uv_version() -> str:
    metadata: object = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise TypeError("project metadata must be a table")
    tool = metadata.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    requirement: object = uv.get("required-version") if isinstance(uv, dict) else None
    if not isinstance(requirement, str) or not re.fullmatch(r"==\d+\.\d+\.\d+", requirement):
        raise AssertionError("uv must use an exact semantic version")
    return requirement.removeprefix("==")


def _native_run(
    root: Path, environment: dict[str, str], command: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    """Exercise the real selected toolchain without inheriting project discovery."""
    return subprocess.run(
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def test_native_tool_diagnostics_are_utf8_even_under_an_ambient_legacy_codec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp936")
    probe = (
        "import sys; sys.stdout.buffer.write(bytes([0xE2, 0x82, 0xAC])); "
        "sys.stderr.buffer.write(bytes([0xE2, 0x82, 0xAC])); sys.exit(7)"
    )
    completed = _native_run(tmp_path, dict(os.environ), (sys.executable, "-c", probe))
    assert completed.returncode == 7
    assert completed.stdout == "\u20ac"
    assert completed.stderr == "\u20ac"


@pytest.fixture
def native_python_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Own a dependency-free native project under a nested path containing spaces."""
    root = tmp_path / "project with spaces" / "nested"
    root.mkdir(parents=True)
    for name in ("mise.toml", "mise.lock"):
        (root / name).write_bytes((ROOT / name).read_bytes())
    (root / "pyproject.toml").write_text(
        '[project]\nname = "native-environment-contract"\nversion = "0.0.0"\n'
        'requires-python = ">=3.12"\ndependencies = []\n\n'
        "[dependency-groups]\nquality = []\n\n"
        f'[tool.uv]\nrequired-version = "=={_required_uv_version()}"\n',
        encoding="utf-8",
    )
    global_config = tmp_path / "global.toml"
    global_config.write_text("", encoding="utf-8")
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("MISE_CONFIG", "MISE_GLOBAL", "MISE_CEILING", "UV_"))
        and name not in {"VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"}
    }
    environment.update(
        MISE_GLOBAL_CONFIG_FILE=str(global_config),
        MISE_SYSTEM_CONFIG_DIR=str(tmp_path / "absent-system"),
        MISE_CEILING_PATHS=str(tmp_path),
        MISE_TRUSTED_CONFIG_PATHS=str(tmp_path),
        MISE_AUTO_INSTALL="0",
        MISE_OFFLINE="1",
        UV_OFFLINE="true",
        UV_PYTHON_DOWNLOADS="never",
    )
    locked = _native_run(root, environment, ("mise", "exec", "--locked", "--", "uv", "lock"))
    assert locked.returncode == 0, locked.stderr
    assert "warning" not in locked.stderr.lower(), locked.stderr
    return root, environment


class TestVerificationContracts:
    """Keep verification on mature tools and the released product artifact."""

    @pytest.mark.parametrize("initial", [None, b"stale\n", b"current\n"])
    def test_ci_projection_checks_then_restores_only_owned_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, initial: bytes | None
    ) -> None:
        path = tmp_path / "nested" / "workflow.yml"
        foreign = tmp_path / "notes.txt"
        foreign.write_bytes(b"user owned\n")
        if initial is not None:
            path.parent.mkdir()
            path.write_bytes(initial)
        monkeypatch.setattr(project, "ROOT", tmp_path)
        monkeypatch.setattr(project, "PROJECTIONS", (project.Projection(path, "workflow"),))
        monkeypatch.setattr(project, "render", lambda _expression: b"current\n")

        if initial == b"current\n":
            project.main(())
        else:
            with pytest.raises(
                SystemExit, match=re.escape("projection drift: nested/workflow.yml")
            ):
                project.main(())
        assert (path.read_bytes() if path.exists() else None) == initial
        project.main(("--write",))
        assert path.read_bytes() == b"current\n"
        project.main(())
        assert foreign.read_bytes() == b"user owned\n"
        assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == {
            Path("notes.txt"),
            Path("nested"),
            Path("nested/workflow.yml"),
        }

    def test_ci_projection_renderer_binds_the_locked_repository(self, mocker) -> None:
        command = mocker.patch.object(
            project.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"yaml\n")
        )

        assert project.render("workflow") == b"yaml\n"

        args = command.call_args.args[0]
        assert args[:5] == ("mise", "exec", "--locked", "--", "cue")
        assert args[5:] == (
            "export",
            str(project.MODEL),
            "--expression",
            "workflow",
            "--out",
            "yaml",
        )
        assert command.call_args.kwargs["check"] is True
        assert command.call_args.kwargs["cwd"] == project.ROOT
        assert command.call_args.kwargs["env"]["MISE_CONFIG_FILE"] == str(project.MISE)
        command.side_effect = subprocess.CalledProcessError(1, args)
        with pytest.raises(subprocess.CalledProcessError):
            project.render("workflow")

    def test_pytest_is_the_only_behavior_test_runner(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        quality = metadata["dependency-groups"]["quality"]
        assert any(requirement.startswith("pytest==") for requirement in quality)
        assert any(requirement.startswith("pytest-mock==") for requirement in quality)
        pytest_config = tomllib.loads((ROOT / "pytest.toml").read_text(encoding="utf-8"))["pytest"]
        assert pytest_config["addopts"] == [
            "--import-mode=importlib",
            "--strict-config",
            "--strict-markers",
        ]
        assert pytest_config["cache_dir"] == ".cache/pytest"
        assert pytest_config["tmp_path_retention_policy"] == "none"
        assert pytest_config["tmp_path_retention_count"] == "0"
        assert pytest_config["filterwarnings"] == ["error"]
        assert (
            "native_distribution: requires the self-contained released executable"
            in pytest_config["markers"]
        )
        assert pytest_config["python_classes"] == ["Test*", "*Tests", "*Contracts"]
        assert pytest_config["testpaths"] == ["tests"]
        direct_test_commands = []
        for relative in (
            ".gitlab-ci.yml",
            ".github/workflows/admission.yml",
            ".github/workflows/verify.yml",
            "noxfile.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            for lineno, line in enumerate(source.splitlines(), 1):
                if "python tests/" in line or '"-m", "tests.' in line:
                    direct_test_commands.append(f"{relative}:{lineno}:{line.strip()}")
        assert direct_test_commands == []
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        metadata_job = gitlab.split("verify-accepted-source:", 1)[1].split(
            "verify-release-tag:", 1
        )[0]
        assert "*install-uv" not in metadata_job
        assert (
            "uv sync --locked --group quality --python python --no-python-downloads" in metadata_job
        )
        assert "uv sync --locked --all-groups" not in metadata_job
        locked_python = "uv run --locked --no-sync --python python --no-python-downloads"
        assert "python tools/" not in metadata_job.replace(f"{locked_python} python tools/", "")
        assert f"{locked_python} python -m tools.release.metadata" in metadata_job
        assert f"{locked_python} python -m tools.quality.repository" in metadata_job
        assert "python -m pytest" not in metadata_job

    def test_uv_cache_writers_are_scoped_to_job_and_matrix_member(self) -> None:
        jobs = _mapping(_load_yaml(ROOT / ".github/workflows/verify.yml")["jobs"])
        writers = []
        for job_value in jobs.values():
            steps = _mapping(job_value)["steps"]
            assert isinstance(steps, list)
            for step_value in steps:
                step = _mapping(step_value)
                if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                    writers.append(_mapping(step.get("with", {})))
        assert writers
        for settings in writers:
            assert settings.get("cache-suffix") == "${{ github.job }}-${{ strategy.job-index }}"

    def test_forge_bootstrap_derives_uv_requirement_from_project_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirement = metadata["tool"]["uv"]["required-version"]
        assert requirement.startswith("==")

        for relative in (".github/workflows/verify.yml", ".gitlab-ci.yml"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert f"uv{requirement}" not in source
            assert re.search(r"\buv==\d", source) is None

        github = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        assert "astral-sh/setup-uv@" in github
        assert "version:" not in "\n".join(
            line for line in github.splitlines() if "setup-uv" in line or "uv-version" in line
        )

        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        uv_version = requirement.removeprefix("==")
        assert gitlab.count(f"ghcr.io/astral-sh/uv:{uv_version}-python") == 2
        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        assert toolchain["tools"]["uv"] == uv_version
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        job_scripts = {
            job: tuple(value.get("before_script", ()))
            for job, value in pipeline.items()
            if isinstance(value, dict) and "before_script" in value
        }
        assert job_scripts
        for job, scripts in job_scripts.items():
            metadata_checks = sum('["tool"]["uv"]["required-version"]' in item for item in scripts)
            if job.removesuffix("-review") in {
                "source-and-governance",
                "verify-macos-native",
                "verify-macos-native-review",
                "verify-windows-native",
                "verify-windows-native-review",
            }:
                assert metadata_checks == 0
                if job.removesuffix("-review") == "source-and-governance":
                    assert scripts[:3] == (
                        "apt-get update -qq",
                        "apt-get install -qq -y --no-install-recommends libatomic1",
                        "mise install --locked",
                    )
                    assert scripts[3:5] == ("npm ci --ignore-scripts", "npm audit signatures")
                else:
                    assert scripts[0] == "mise install --locked"
                    assert "mise exec --locked -- uv sync --locked --group quality" in scripts
                continue
            assert metadata_checks == 1
        assert 'UV_VERSION="${UV_VERSION#uv }"' in gitlab
        assert 'ACTUAL_UV_VERSION="${UV_VERSION%% *}"' in gitlab
        assert 'EXPECTED_UV_VERSION="${UV_REQUIREMENT#==}"' in gitlab
        assert "uv version mismatch: expected %s, actual %s" in gitlab
        assert "&install-uv" not in gitlab
        assert "*install-uv" not in gitlab
        assert "python -m pip install" not in gitlab

    @pytest.mark.parametrize(
        ("reported_version", "expected_returncode"),
        [
            (f"uv {_required_uv_version()} (x86_64-unknown-linux-musl)", 0),
            ("uv 9.9.9 (x86_64-unknown-linux-musl)", 1),
        ],
    )
    @pytest.mark.skipif(os.name == "nt", reason="GitLab executes this contract with POSIX sh")
    def test_gitlab_uv_contract_uses_the_machine_version_token(
        self, tmp_path: Path, reported_version: str, expected_returncode: int
    ) -> None:
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        verify_python = _mapping(pipeline["verify-python"])
        before_script = verify_python["before_script"]
        assert isinstance(before_script, list)
        script = next(
            item
            for item in before_script
            if isinstance(item, str)
            if '["tool"]["uv"]["required-version"]' in item
        )
        executable = tmp_path / "uv"
        executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{reported_version}'\n")
        executable.chmod(0o700)

        completed = subprocess.run(
            ["/bin/sh", "-eu", "-c", script],
            cwd=ROOT,
            env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
            check=False,
        )

        assert completed.returncode == expected_returncode

    def test_test_suite_has_no_unittest_compatibility_surface(self) -> None:
        offenders = []
        for path in sorted((ROOT / "tests").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Import)
                    and any(
                        alias.name == "unittest" or alias.name.startswith("unittest.")
                        for alias in node.names
                    )
                ) or (
                    isinstance(node, ast.ImportFrom)
                    and (
                        node.module == "unittest"
                        or (node.module is not None and node.module.startswith("unittest."))
                    )
                ):
                    offenders.append(f"{relative}:{node.lineno}:unittest_import")
                elif isinstance(node, ast.ClassDef) and any(
                    (isinstance(base, ast.Name) and base.id == "TestCase")
                    or (
                        isinstance(base, ast.Attribute)
                        and isinstance(base.value, ast.Name)
                        and base.value.id == "unittest"
                        and base.attr == "TestCase"
                    )
                    for base in node.bases
                ):
                    offenders.append(f"{relative}:{node.lineno}:testcase_inheritance")
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "unittest"
                    and node.func.attr == "main"
                ):
                    offenders.append(f"{relative}:{node.lineno}:unittest_main")
                elif (
                    isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
                ):
                    offenders.append(f"{relative}:{node.lineno}:direct_test_entrypoint")
        assert offenders == []

    def test_root_pytest_toml_is_discovered_without_invocation_flags(self, tmp_path: Path) -> None:
        config = tmp_path / "pytest.toml"
        config.write_bytes((ROOT / "pytest.toml").read_bytes())
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_discovery.py").write_text(
            "class SampleContracts:\n    def test_native_discovery(self):\n        assert True\n",
            encoding="utf-8",
        )
        command = [sys.executable, "-m", "pytest", "--collect-only", "-vv"]
        environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        discovered = subprocess.run(
            command,
            cwd=tmp_path,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert discovered.returncode == 0, discovered.stderr
        assert f"rootdir: {tmp_path}" in discovered.stdout
        assert "configfile: pytest.toml" in discovered.stdout
        assert "1 test collected" in discovered.stdout

    def test_native_distribution_tests_are_explicit_and_release_owned(self) -> None:
        pytest_config = tomllib.loads((ROOT / "pytest.toml").read_text(encoding="utf-8"))["pytest"]
        assert (
            "native_distribution: requires the self-contained released executable"
            in pytest_config["markers"]
        )
        source = (ROOT / "tests/service/handoff/test_subprocess.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        pytestmark = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            )
        )
        assert isinstance(pytestmark.value, ast.List)
        markers = {ast.unparse(element) for element in pytestmark.value.elts}

        lifecycle = (ROOT / "tests/release/test_native_lifecycle.py").read_text(encoding="utf-8")
        lifecycle_tree = ast.parse(lifecycle)
        lifecycle_marks = next(
            node
            for node in lifecycle_tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            )
        )
        assert isinstance(lifecycle_marks.value, ast.List)
        assert not any("skipif" in ast.unparse(element) for element in lifecycle_marks.value.elts)
        assert "pytest.skip" not in lifecycle
        assert "pytest.mark.native_distribution" in markers
        assert "pytest.mark.usefixtures(preserve_native_host_projection.__name__)" in markers

    def test_quality_environment_is_repository_owned_and_locked(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirements = metadata["dependency-groups"]["quality"]
        names = [requirement.partition("==")[0] for requirement in requirements]
        assert set(names) == {
            "coverage",
            "deptry",
            "hatchling",
            "nox",
            "pyperf",
            "pytest",
            "pytest-mock",
            "pytest-subtests",
            "pyyaml",
            "ruff",
            "semver",
            "ty",
            "vulture",
        }
        assert len(names) == len(set(names))
        assert all(
            name and separator == "==" and version
            for name, separator, version in (
                requirement.partition("==") for requirement in requirements
            )
        )
        assert re.fullmatch(r"==\d+\.\d+\.\d+", metadata["tool"]["uv"]["required-version"])
        assert metadata["tool"]["uv"]["link-mode"] == "copy"
        assert (ROOT / "uv.lock").is_file()

        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        assert toolchain["settings"] == {
            "idiomatic_version_file_enable_tools": [],
            "legacy_version_file": False,
            "locked": True,
            "not_found_system_fallback": False,
            "use_versions_host": False,
        }

    def test_native_release_tools_are_isolated_from_quality(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        groups = metadata["dependency-groups"]
        quality = {requirement.partition("==")[0] for requirement in groups["quality"]}
        release = {requirement.partition("==")[0] for requirement in groups["release"]}

        assert quality.isdisjoint(release)
        assert release == {"pyinstaller"}

    def test_developer_bootstrap_installs_product_and_quality_groups(self) -> None:
        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        environment = toolchain["env"]
        assert environment["UV_PROJECT_ENVIRONMENT"] == "{{config_root}}/.venv"
        assert environment["VIRTUAL_ENV"] is False
        assert environment["UV_PYTHON"] == {
            "value": "{% if tools.python is defined %}{{tools.python.path}}{% endif %}",
            "tools": True,
        }
        assert environment["PYTHONHOME"] is False
        assert environment["PYTHONPATH"] is False
        assert environment["PYTHONNOUSERSITE"] == "1"
        assert toolchain["tasks"]["bootstrap"]["run"] == [
            "uv sync --locked --all-groups",
            "npm ci --ignore-scripts",
            "npm audit signatures",
        ]
        assert toolchain["tasks"]["toolchain:verify"]["run"] == [
            f"mise which {name}"
            for name in (
                "node",
                "python",
                "uv",
                "npm",
                "cue",
                "taplo",
                "gitleaks",
                "actionlint",
                "lychee",
                "vale",
                "gh",
                "glab",
            )
        ]
        for task in ("bootstrap", "quick", "check", "native", "release"):
            assert toolchain["tasks"][task]["depends"] == ["toolchain:verify"]
        for relative in ("AGENTS.md", "CONTRIBUTING.md", "README.md"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert "mise run bootstrap" in source
            assert "mise run check" in source

    @pytest.mark.parametrize(
        ("task", "session"),
        [
            ("quick", "quick"),
            ("check", "full"),
            ("native", "release"),
            ("release", "release_asset"),
        ],
    )
    def test_developer_tasks_delegate_to_existing_verification(
        self, task: str, session: str
    ) -> None:
        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        assert toolchain["tasks"][task]["run"] == (
            "uv run --locked --group quality nox -s " + session
        )

    @pytest.mark.parametrize(
        ("relative", "source", "expected"),
        [
            (
                "src/codex_responses_proxy/probe.py",
                "def answer():\n    return 42\n",
                {"D100", "D103"},
            ),
            ("tools/probe.py", "def answer():\n    return 42\n", {"D100", "D103"}),
            ("noxfile.py", "def answer():\n    return 42\n", {"D100", "D103"}),
            ("tests/probe.py", "def answer():\n    return 42\n", set()),
            (
                "tests/probe.py",
                'def answer():\n    """Return the answer"""\n    return 42\n',
                {"D415"},
            ),
        ],
    )
    def test_native_ruff_applies_documentation_policy_by_semantic_role(
        self, relative: str, source: str, expected: set[str]
    ) -> None:
        result = subprocess.run(
            (
                "ruff",
                "check",
                "--config",
                str(ROOT / ".config/quality/native/ruff.toml"),
                "--output-format",
                "json",
                "--stdin-filename",
                str(ROOT / relative),
                "-",
            ),
            input=source,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == bool(expected), result.stderr
        assert {item["code"] for item in json.loads(result.stdout)} == expected

    def test_repository_declares_the_supported_python_matrix_once(self) -> None:
        github = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        supported = (ROOT / ".python-versions").read_text(encoding="utf-8").splitlines()
        uv_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
            "uv"
        ]["required-version"].removeprefix("==")
        image_pattern = re.compile(
            r"^ghcr\.io/astral-sh/uv:(?P<uv>\d+\.\d+\.\d+)-python"
            r"(?P<minor>\d+\.\d+)-trixie-slim"
            r"@sha256:(?P<digest>[0-9a-f]{64})$"
        )
        image_values = dict(
            re.findall(r"^  (UV_PYTHON_(?:FLOOR|LATEST)_IMAGE): (\S+)$", gitlab, re.MULTILINE)
        )
        assert set(image_values) == {"UV_PYTHON_FLOOR_IMAGE", "UV_PYTHON_LATEST_IMAGE"}
        floor_image = image_pattern.fullmatch(image_values["UV_PYTHON_FLOOR_IMAGE"])
        latest_image = image_pattern.fullmatch(image_values["UV_PYTHON_LATEST_IMAGE"])
        assert floor_image is not None
        assert latest_image is not None
        assert floor_image.group("uv") == uv_version
        assert latest_image.group("uv") == uv_version
        assert floor_image.group("minor") == supported[0]
        assert latest_image.group("minor") == supported[-1]
        assert "python -m tools.quality.python_matrix" in github
        assert 'print(f"floor={versions[0]}"' not in github
        assert 'print(f"latest={versions[-1]}"' not in github
        assert "needs.python-matrix.outputs.floor" in github
        assert "needs.python-matrix.outputs.latest" in github
        assert "needs.python-matrix.outputs.release" in github
        assert "python-version: ${{ needs.python-matrix.outputs.release }}" in github
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        assert _mapping(pipeline["default"])["image"] == {"name": "$UV_PYTHON_LATEST_IMAGE"}
        assert _mapping(pipeline["verify-python-quality"])["image"] == {
            "name": "$UV_PYTHON_FLOOR_IMAGE"
        }
        assert "LINUX_RELEASE_IMAGE" not in gitlab

    def test_release_collects_ctypes_as_source_outside_the_pyz_archive(self) -> None:
        """Avoid marshal identity drift in the Python 3.14 ``ctypes`` code object."""
        hook = ROOT / "tools" / "release" / "hooks" / "hook-ctypes.py"

        hook_tree = ast.parse(hook.read_text(encoding="utf-8"))
        executable_statements = hook_tree.body[1:]

        assert ast.get_docstring(hook_tree)
        assert len(executable_statements) == 1
        assignment = executable_statements[0]
        assert isinstance(assignment, ast.Assign)
        assert [target.id for target in assignment.targets if isinstance(target, ast.Name)] == [
            "module_collection_mode"
        ]
        assert ast.literal_eval(assignment.value) == "py"

    def test_forge_quality_jobs_use_the_locked_runner(self) -> None:
        github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        quality_job = github.split("  python-quality:", 1)[1].split("  native-assets:", 1)[0]
        assert "uv run --locked --group quality nox -s quality" in quality_job
        assert "uv sync --locked --only-group quality" not in quality_job
        assert "uv sync --locked --group quality --python python --no-python-downloads" in gitlab
        assert (
            "uv run --locked --no-sync --python python --no-python-downloads nox -s quality"
            in gitlab
        )
        assert "fetch-depth: 0" in quality_job
        assert "fetch-tags: true" in quality_job
        assert "python -m tools.quality.repository" not in quality_job
        assert "uv run --locked --group quality nox -s quality" in github
        assert "python -m tools.quality.repository" in gitlab

    def test_hosted_governance_tools_use_the_complete_locked_environment(self) -> None:
        github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        source = gitlab.split("source-and-governance:", 1)[1].split("verify-python:", 1)[0]
        assert "uv sync --locked --group quality --python python --no-python-downloads" in source
        assert "uv sync --locked --all-groups" in github

    def test_performance_is_an_independent_locked_proof_surface(self) -> None:
        """Performance must be measured explicitly, not inferred from functional tests."""
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        quality = metadata["dependency-groups"]["quality"]
        assert "pyperf==2.10.0" in quality
        assert (ROOT / ".config/quality/policy/performance.toml").is_file()
        assert (ROOT / "tools/performance/benchmark.py").is_file()
        assert (ROOT / "tools/performance/memory.py").is_file()

        github = _load_yaml(ROOT / ".github/workflows/verify.yml")
        gitlab = _load_yaml(ROOT / ".gitlab-ci.yml")
        github_jobs = _mapping(github["jobs"])
        assert "performance" in github_jobs
        assert "uv run --locked --group quality nox -s performance" in str(
            github_jobs["performance"]
        )
        assert "verify-performance" in gitlab
        assert "nox -s performance" in str(gitlab["verify-performance"])


def test_package_manager_has_native_precedence_over_bundled_npm() -> None:
    configuration = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert configuration["tool_alias"]["npm"] == "npm:npm"
    assert configuration["tools"]["npm"] == "12.2.0"
    model = (ROOT / ".config/ci/pipeline.cue").read_text(encoding="utf-8")
    assert 'quality:         "python,uv,node,npm,' in model


def test_operator_forge_cli_is_bound_to_the_existing_toolchain() -> None:
    configuration = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert configuration["tools"]["glab"] == "1.120.0"
    assert "mise which glab" in configuration["tasks"]["toolchain:verify"]["run"]


def test_gitlab_linux_tags_bind_directly_without_recursive_aliases() -> None:
    """Each event selects a single-level native scheduling variable."""
    pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
    for name in (
        "source-and-governance",
        "verify-python",
        "verify-python-quality",
        "verify-performance",
    ):
        for suffix, selector in (
            ("", "$CODEX_RESPONSES_PROXY_GITLAB_LINUX_RUNNER_TAG"),
            ("-review", "$CODEX_RESPONSES_PROXY_GITLAB_LINUX_REVIEW_RUNNER_TAG"),
        ):
            job = _mapping(pipeline[name + suffix])
            assert job["tags"] == [selector]
            assert "CODEX_RESPONSES_PROXY_GITLAB_LINUX_JOB_TAG" not in str(job["rules"])
            event = str(job["rules"])
            assert ("merge_request_event" in event) == bool(suffix)
    assert "CODEX_RESPONSES_PROXY_GITLAB_LINUX_JOB_TAG" not in str(pipeline)


@pytest.mark.parametrize(
    "job_name",
    [
        "verify-macos-native",
        "verify-macos-native-review",
        "verify-windows-native",
        "verify-windows-native-review",
    ],
)
def test_native_ci_uses_the_single_tool_bound_environment(job_name: str) -> None:
    pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
    job = _mapping(pipeline[job_name])
    bootstrap = job["before_script"]
    scripts = job["script"]
    assert isinstance(bootstrap, list)
    assert isinstance(scripts, list)
    sync = [entry for entry in bootstrap if isinstance(entry, str) and "uv sync" in entry]
    assert sync == ["mise exec --locked -- uv sync --locked --group quality"]
    assert all(
        isinstance(entry, str) and "uv run --locked --group quality" in entry for entry in scripts
    )
    assert "--no-sync" not in str(scripts)
    assert "--python" not in str(scripts)
    assert (
        "mise exec --locked -- uv run --locked --group quality python -m pytest -q "
        "-m repository_toolchain tests/quality/test_verification.py"
    ) in scripts


@pytest.mark.repository_toolchain
def test_native_environment_resolves_the_locked_python_owner(
    native_python_project: tuple[Path, dict[str, str]],
) -> None:
    root, environment = native_python_project
    discovered = _native_run(root, environment, ("mise", "config", "--json"))
    assert discovered.returncode == 0, discovered.stderr
    assert {Path(item["path"]) for item in json.loads(discovered.stdout)} == {
        root / "mise.toml",
        root.parents[1] / "global.toml",
    }
    selected = _native_run(root, environment, ("mise", "env", "--json"))
    assert selected.returncode == 0, selected.stderr
    assert selected.stderr == ""
    native = json.loads(selected.stdout)
    assert Path(native["UV_PROJECT_ENVIRONMENT"]) == root / ".venv"
    assert Path(native.get("UV_PYTHON", "")).is_absolute(), native.get("UV_PYTHON")
    toolchain = tomllib.loads((root / "mise.toml").read_text(encoding="utf-8"))
    assert Path(native["UV_PYTHON"]).name == toolchain["tools"]["python"]


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("tools", ["python,uv", "gh"])
def test_native_environment_binding_applies_only_to_the_selected_tool_plane(
    native_python_project: tuple[Path, dict[str, str]], tools: str
) -> None:
    root, environment = native_python_project
    observed = _native_run(
        root, {**environment, "MISE_ENABLE_TOOLS": tools}, ("mise", "env", "--json")
    )
    assert observed.returncode == 0, observed.stderr
    assert observed.stderr == ""
    selected = json.loads(observed.stdout)
    if tools == "gh":
        assert not selected.get("UV_PYTHON"), selected.get("UV_PYTHON")
    else:
        assert Path(selected["UV_PYTHON"]).is_absolute()
    assert Path(selected["UV_PROJECT_ENVIRONMENT"]) == root / ".venv"


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("consumer", ["proof", "native-ci"])
@pytest.mark.parametrize("state", ["ready", "missing", "stale", "stale-lock"])
def test_native_uv_execution_normalizes_only_its_owned_environment(
    native_python_project: tuple[Path, dict[str, str]], consumer: str, state: str
) -> None:
    root, environment = native_python_project
    profile = tomllib.loads((ROOT / ".ethos/profile.toml").read_text(encoding="utf-8"))
    if consumer == "proof":
        command = profile["proof"]["gates"][0]["command"]
        prefix = tuple(command[: command.index("nox")])
    else:
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        scripts = _mapping(pipeline["verify-windows-native"])["script"]
        assert isinstance(scripts, list)
        command = next(item for item in scripts if isinstance(item, str) and "nox -s" in item)
        prefix = tuple(command.split(" nox -s", 1)[0].split())
    local = root / ".venv"
    if state != "missing":
        created = _native_run(
            root, environment, ("mise", "exec", "--locked", "--", "uv", "venv", str(local))
        )
        assert created.returncode == 0, created.stderr
    if state == "stale":
        config = local / "pyvenv.cfg"
        config.write_text(
            re.sub(r"version_info = [^\n]+", "version_info = 0.0.0", config.read_text()),
            encoding="utf-8",
        )
    if state == "stale-lock":
        metadata = root / "pyproject.toml"
        metadata.write_text(metadata.read_text().replace('version = "0.0.0"', 'version = "0.0.1"'))
    preserved = {
        name: (root / name).read_bytes()
        for name in ("mise.toml", "mise.lock", "pyproject.toml", "uv.lock")
    }
    probe = (
        "import json, sys; "
        "print(json.dumps({'version': list(sys.version_info[:3]), 'prefix': sys.prefix}))"
    )
    observed = _native_run(root, environment, (*prefix, "python", "-c", probe))
    if state == "stale-lock":
        assert observed.returncode != 0, observed.stdout
        assert observed.stdout == ""
    else:
        assert observed.returncode == 0, observed.stderr
        assert "warning" not in observed.stderr.lower(), observed.stderr
        actual = json.loads(observed.stdout)
        expected = tomllib.loads(preserved["mise.toml"].decode())["tools"]["python"]
        assert actual["version"] == [int(part) for part in expected.split(".")]
        assert Path(actual["prefix"]) == local
    assert {name: (root / name).read_bytes() for name in preserved} == preserved
