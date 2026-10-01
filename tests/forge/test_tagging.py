"""Portable local product-tag publication contracts."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from tools.forge import context
from tools.forge import tag_signature
from tools.git_environment import isolated_config_environment
from tools.release import tag


def _run(*args: str, cwd: Path, environment: dict[str, str] | None = None) -> str:
    return subprocess.run(
        args,
        cwd=cwd,
        env=isolated_config_environment(environment),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(params=[False, True], ids=["native-home", "deep-home"])
def tag_fixture(request, monkeypatch):
    """Create one signed source and two independent peers without personal state."""
    if os.name == "nt" or any(shutil.which(name) is None for name in ("ssh-agent", "ssh-add")):
        pytest.skip("OpenSSH agent integration is unavailable")
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        if request.param:
            home = root / ("isolated-home-" * 10)
            home.mkdir()
            monkeypatch.setenv("HOME", str(home))
        source, gitlab, github, key = (
            root / "source",
            root / "gitlab.git",
            root / "github.git",
            root / "signing",
        )
        anchor, publication = root / "allowed-signers", root / "publication.toml"
        _run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), cwd=root)
        public = " ".join(key.with_suffix(".pub").read_text().split()[:2])
        fingerprint = _run(
            "ssh-keygen", "-lf", str(key.with_suffix(".pub")), "-E", "sha256", cwd=root
        ).split()[1]
        anchor.write_text(f'publisher@example.test namespaces="git" {public}\n')
        publication.write_text(
            'schema-version = 1\n[product]\nactor-name = "Publisher"\n'
            'actor-email = "publisher@example.test"\n'
            f'active-signing-fingerprint = "{fingerprint}"\n',
            encoding="utf-8",
        )
        for remote in (gitlab, github):
            _run("git", "init", "-q", "--bare", str(remote), cwd=root)
        _run("git", "init", "-q", "-b", "main", str(source), cwd=root)
        _run("git", "config", "core.hooksPath", os.devnull, cwd=source)
        _run("git", "config", "user.name", "Fixture", cwd=source)
        _run("git", "config", "user.email", "fixture@example.test", cwd=source)
        (source / "tools/release").mkdir(parents=True)
        (source / "tools/forge").mkdir(parents=True)
        (source / "tools/__init__.py").touch()
        (source / "tools/release/__init__.py").touch()
        (source / "tools/release/metadata.py").write_text(
            "import sys\nraise SystemExit(0 if '--prepare-release' in sys.argv or '--tag' in sys.argv else 1)\n"
        )
        (source / "VERSION").write_text("1.0.0\n")
        _run("git", "add", ".", cwd=source)
        _run("git", "commit", "-qm", "release", cwd=source)
        _run("git", "remote", "add", "gitlab", str(gitlab), cwd=source)
        _run("git", "remote", "add", "github", str(github), cwd=source)
        native_temp = subprocess.run(
            [sys.executable, "-I", "-c", "import tempfile; print(tempfile.gettempdir())"],
            env={
                key: value
                for key, value in os.environ.items()
                if key not in {"TMPDIR", "TEMP", "TMP"}
            },
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory(dir=native_temp) as socket_root:
            socket = Path(socket_root) / "agent"
            agent = subprocess.Popen(
                ["ssh-agent", "-D", "-a", str(socket)],
                cwd=root,
                env=isolated_config_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            environment = {
                "SSH_AUTH_SOCK": str(socket),
                "SSH_AGENT_PID": str(agent.pid),
            }
            try:
                deadline = time.monotonic() + 5
                while not socket.exists() and agent.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert socket.exists()
                assert agent.poll() is None
                _run("ssh-add", str(key), cwd=root, environment=environment)
                monkeypatch.setenv("SSH_AUTH_SOCK", environment["SSH_AUTH_SOCK"])
                monkeypatch.setenv("SSH_AGENT_PID", environment["SSH_AGENT_PID"])
                yield source, gitlab, github, publication, anchor
            finally:
                if agent.poll() is None:
                    agent.terminate()
                try:
                    agent.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    agent.kill()
                    agent.communicate(timeout=5)
                assert not socket.exists()


def test_local_tag_is_signed_once_and_identical_on_both_peers(tag_fixture) -> None:
    source, gitlab, github, publication, anchor = tag_fixture
    oid = tag.create(
        root=source,
        provider="gitlab",
        tag="v1.0.0",
        remote="gitlab",
        publication_context=publication,
        anchor=anchor,
    )
    assert not (source / "tools/release/__pycache__").exists()
    github_oid = tag.create(
        root=source,
        provider="github",
        tag="v1.0.0",
        remote="github",
        publication_context=publication,
        anchor=anchor,
    )
    local_oid = _run("git", "rev-parse", "refs/tags/v1.0.0", cwd=source)
    assert oid == github_oid == local_oid
    assert oid == _run("git", "rev-parse", "refs/tags/v1.0.0", cwd=gitlab)
    assert oid == _run("git", "rev-parse", "refs/tags/v1.0.0", cwd=github)
    tag_signature.verify(source, "v1.0.0", anchor)
    _run(
        "git",
        "update-ref",
        "refs/tags/v1.0.0",
        _run("git", "rev-parse", "refs/heads/main", cwd=source),
        cwd=gitlab,
    )
    with pytest.raises(tag.TagError, match="differs from local"):
        tag.create(
            root=source,
            provider="gitlab",
            tag="v1.0.0",
            remote="gitlab",
            publication_context=publication,
            anchor=anchor,
        )


def test_context_and_signature_fail_closed(tag_fixture) -> None:
    source, _, _, publication, anchor = tag_fixture
    publication.write_text('schema-version = 1\n[other]\nvalue = "invalid"\n', encoding="utf-8")
    with pytest.raises(context.PublicationContextError):
        context.load(publication)
    with pytest.raises(tag_signature.TagSignatureError):
        tag_signature.verify(source, "latest", anchor)


@pytest.mark.parametrize(
    "mode", ["invalid-provider", "dirty", "malformed-remote", "changed-readback"]
)
def test_tag_publication_stops_on_invalid_source_or_remote_identity(mode, tmp_path, mocker):
    oid = "a" * 40
    outputs = {
        "dirty": ["dirty"],
        "malformed-remote": ["", "v1.2.3", oid, "malformed"],
        "changed-readback": ["", "v1.2.3", oid, "", "", "wrong refs/tags/v1.2.3"],
        "invalid-provider": [],
    }
    run = mocker.patch.object(tag, "_run", side_effect=outputs[mode])
    mocker.patch.object(tag.context, "load")
    mocker.patch.object(tag, "_metadata")
    mocker.patch.object(tag.tag_signature, "verify")
    with pytest.raises(tag.TagError):
        tag.create(
            root=tmp_path,
            provider="unknown" if mode == "invalid-provider" else "github",
            tag="v1.2.3",
            remote="peer",
            publication_context=tmp_path / "context",
            anchor=tmp_path / "anchor",
        )
    if mode == "invalid-provider":
        run.assert_not_called()


@pytest.mark.parametrize(
    "failure", [OSError("missing"), subprocess.CalledProcessError(1, ["git"], stderr="failed")]
)
def test_tag_transport_translates_failure_without_retry(tmp_path, failure, mocker):
    mocker.patch.object(tag.subprocess, "run", side_effect=failure)
    with pytest.raises(tag.TagError):
        tag._run(tmp_path, "status")
    with pytest.raises(tag.TagError, match="metadata validation failed"):
        tag._metadata(tmp_path, "--prepare-release")


def test_tag_signature_requires_anchor_and_preserves_cli_failure(tmp_path, mocker, capsys):
    anchor = tmp_path / "anchor"
    with pytest.raises(tag_signature.TagSignatureError, match="anchor is unavailable"):
        tag_signature.verify(tmp_path, "v1.2.3", anchor)
    anchor.write_text("external trust")
    run = mocker.patch.object(tag_signature.subprocess, "run")
    args = (str(tmp_path), "v1.2.3", str(anchor))
    tag_signature.main(args)
    assert "signature: OK" in capsys.readouterr().out
    assert run.call_count == 2
    run.side_effect = OSError("missing")
    with pytest.raises(SystemExit) as stopped:
        tag_signature.main(args)
    assert stopped.value.code == 1
    assert "signature is invalid" in capsys.readouterr().err


@pytest.mark.parametrize("provider", ["gitlab", "github"])
def test_tag_cli_uses_one_selected_peer(provider, tmp_path, mocker, capsys):
    create = mocker.patch.object(tag, "create", return_value="a" * 40)
    args = (
        "--provider",
        provider,
        "--tag",
        "v1.2.3",
        "--publication-context",
        str(tmp_path / "context"),
        "--anchor",
        str(tmp_path / "anchor"),
    )
    tag.main(args)
    assert f"{provider} release tag synchronized" in capsys.readouterr().out
    assert create.call_args.kwargs["remote"] == ("origin" if provider == "gitlab" else "github")
    create.side_effect = tag.TagError("rejected")
    with pytest.raises(SystemExit) as stopped:
        tag.main(args)
    assert stopped.value.code == 1
    assert "rejected" in capsys.readouterr().err
