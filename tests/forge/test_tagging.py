"""Portable local product-tag publication contracts."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.forge import context, tag_signature
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


@pytest.fixture
def tag_fixture(monkeypatch):
    """Create one signed source and two independent peers without personal state."""

    if os.name == "nt" or any(shutil.which(name) is None for name in ("ssh-agent", "ssh-add")):
        pytest.skip("OpenSSH agent integration is unavailable")
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
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
            yield source, gitlab, github, publication, anchor
        finally:
            _run("ssh-agent", "-k", cwd=root, environment=environment)


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
