"""Portable provider-native release tag contracts."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.forge import context, tag_signature
from tools.release import tag


def _run(*args: str, cwd: Path, environment: dict[str, str] | None = None) -> str:
    value = os.environ.copy()
    value.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    if environment:
        value.update(environment)
    return subprocess.run(
        args, cwd=cwd, env=value, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def tag_fixture(monkeypatch):
    """Create one signed source and provider remote without personal state."""

    if os.name == "nt" or any(shutil.which(name) is None for name in ("ssh-agent", "ssh-add")):
        pytest.skip("OpenSSH agent integration is unavailable")
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        source, remote, key = root / "source", root / "remote.git", root / "signing"
        anchor, publication = root / "allowed-signers", root / "publication.toml"
        _run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), cwd=root)
        public = " ".join(key.with_suffix(".pub").read_text().split()[:2])
        fingerprint = _run(
            "ssh-keygen", "-lf", str(key.with_suffix(".pub")), "-E", "sha256", cwd=root
        ).split()[1]
        anchor.write_text(f'publisher@example.test namespaces="git" {public}\n')
        publication.write_text(
            'schema-version = 1\n[gitlab]\nactor-name = "Publisher"\n'
            'actor-email = "publisher@example.test"\n'
            f'active-signing-fingerprint = "{fingerprint}"\n',
            encoding="utf-8",
        )
        _run("git", "init", "-q", "--bare", str(remote), cwd=root)
        _run("git", "init", "-q", "-b", "main", str(source), cwd=root)
        _run("git", "config", "core.hooksPath", os.devnull, cwd=source)
        _run("git", "config", "user.name", "Fixture", cwd=source)
        _run("git", "config", "user.email", "fixture@example.test", cwd=source)
        (source / "tools/release").mkdir(parents=True)
        (source / "tools/forge").mkdir(parents=True)
        (source / "tools/release/metadata.py").write_text(
            "import sys\nraise SystemExit(0 if '--prepare-release' in sys.argv or '--tag' in sys.argv else 1)\n"
        )
        (source / "VERSION").write_text("1.0.0\n")
        _run("git", "add", ".", cwd=source)
        _run("git", "commit", "-qm", "release", cwd=source)
        _run("git", "remote", "add", "origin", str(remote), cwd=source)
        _run("git", "push", "-q", "origin", "main", cwd=source)
        agent = _run("ssh-agent", "-s", cwd=root)
        environment = {
            key: next(
                line.split("=", 1)[1].split(";", 1)[0]
                for line in agent.splitlines()
                if line.startswith(f"{key}=")
            )
            for key in ("SSH_AUTH_SOCK", "SSH_AGENT_PID")
        }
        _run("ssh-add", str(key), cwd=root, environment=environment)
        monkeypatch.setenv("SSH_AUTH_SOCK", environment["SSH_AUTH_SOCK"])
        monkeypatch.setenv("SSH_AGENT_PID", environment["SSH_AGENT_PID"])
        try:
            yield source, remote, publication, anchor
        finally:
            _run("ssh-agent", "-k", cwd=root, environment=environment)


def test_gitlab_tag_is_signed_verified_and_immutable(tag_fixture) -> None:
    source, remote, publication, anchor = tag_fixture
    oid = tag.create(
        root=source,
        provider="gitlab",
        tag="v1.0.0",
        remote="origin",
        publication_context=publication,
        anchor=anchor,
    )
    assert oid == _run("git", "rev-parse", "refs/tags/v1.0.0", cwd=remote)
    tag_signature.verify(remote, "v1.0.0", "gitlab", anchor)
    with pytest.raises(tag.TagError, match="already exists"):
        tag.create(
            root=source,
            provider="gitlab",
            tag="v1.0.0",
            remote="origin",
            publication_context=publication,
            anchor=anchor,
        )


def test_context_and_signature_fail_closed(tag_fixture) -> None:
    source, _, publication, anchor = tag_fixture
    with pytest.raises(context.PublicationContextError):
        context.load(publication, "github")
    with pytest.raises(tag_signature.TagSignatureError):
        tag_signature.verify(source, "latest", "gitlab", anchor)
