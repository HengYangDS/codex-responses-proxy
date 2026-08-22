"""Exact local-object publication contracts for optional Forge peers."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest

from tools.forge.project import ProjectionError
from tools.forge.project import project
from tools.git_environment import isolated_config_environment


class ForgeFixture(TypedDict):
    """One signed local source and two independent bare peers."""

    source: Path
    gitlab: Path
    github: Path
    anchor: Path
    email: str


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git with isolated user configuration."""

    result = subprocess.run(
        args,
        cwd=cwd,
        env=isolated_config_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def signed_commit(repository: Path, name: str, content: str) -> str:
    """Create one signed fixture commit and return its object ID."""

    (repository / name).write_text(content, encoding="utf-8")
    run("git", "add", name, cwd=repository)
    run("git", "commit", "-qS", "-m", f"test: {name}", cwd=repository)
    return run("git", "rev-parse", "HEAD", cwd=repository).stdout.strip()


@pytest.fixture
def forge_fixture(tmp_path: Path) -> ForgeFixture:
    """Create a portable signed source and two empty peer repositories."""

    if shutil.which("ssh-keygen") is None:
        pytest.skip("OpenSSH signing is unavailable")
    source = tmp_path / "source"
    gitlab = tmp_path / "gitlab.git"
    github = tmp_path / "github.git"
    key = tmp_path / "signing"
    anchor = tmp_path / "allowed-signers"
    email = "product@example.test"
    run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), cwd=tmp_path)
    public = " ".join(key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
    anchor.write_text(f'{email} namespaces="git" {public}\n', encoding="ascii")
    for remote in (gitlab, github):
        run("git", "init", "-q", "--bare", str(remote), cwd=tmp_path)
    run("git", "init", "-q", "-b", "main", str(source), cwd=tmp_path)
    for key_name, value in (
        ("core.hooksPath", os.devnull),
        ("user.name", "Product Publisher"),
        ("user.email", email),
        ("user.useConfigOnly", "true"),
        ("gpg.format", "ssh"),
        ("gpg.ssh.program", "ssh-keygen"),
        ("user.signingkey", str(key)),
    ):
        run("git", "config", key_name, value, cwd=source)
    signed_commit(source, "README.md", "one\n")
    run("git", "branch", "dev", cwd=source)
    run("git", "remote", "add", "origin", str(gitlab), cwd=source)
    run("git", "remote", "add", "github", str(github), cwd=source)
    return {
        "source": source,
        "gitlab": gitlab,
        "github": github,
        "anchor": anchor,
        "email": email,
    }


def publish(fixture: ForgeFixture, provider: str, remote: str, source_ref: str = "main") -> str:
    """Publish through the public projector contract."""

    return project(
        root=fixture["source"],
        provider=provider,
        source_ref=source_ref,
        remote=remote,
        email=fixture["email"],
        allowed_signers=fixture["anchor"],
    )


def tip(repository: Path, branch: str) -> str:
    """Read one bare peer branch tip."""

    return run("git", "rev-parse", f"refs/heads/{branch}", cwd=repository).stdout.strip()


def test_each_optional_peer_receives_the_exact_local_commit(
    forge_fixture: ForgeFixture,
) -> None:
    """Local, GitLab, and GitHub share one immutable commit object."""

    local = run("git", "rev-parse", "main", cwd=forge_fixture["source"]).stdout.strip()
    gitlab = publish(forge_fixture, "gitlab", "origin")
    github = publish(forge_fixture, "github", "github")

    assert gitlab == github == local
    for peer in (forge_fixture["gitlab"], forge_fixture["github"]):
        assert tip(peer, "main") == tip(peer, "dev") == local


def test_new_remote_refs_use_zero_oid_leases(forge_fixture: ForgeFixture, monkeypatch) -> None:
    """A branch absent at observation cannot appear before the atomic push."""

    from tools.forge import project as projector

    calls: list[tuple[str, ...]] = []
    original = projector._git

    def observe(root: Path, *args: str, check: bool = True):
        if args[:2] == ("push", "--atomic"):
            calls.append(args)
        return original(root, *args, check=check)

    monkeypatch.setattr(projector, "_git", observe)
    publish(forge_fixture, "gitlab", "origin")

    assert calls
    zero = "0" * 40
    assert f"--force-with-lease=refs/heads/main:{zero}" in calls[0]
    assert f"--force-with-lease=refs/heads/dev:{zero}" in calls[0]


def test_one_peer_does_not_read_or_require_the_other(
    forge_fixture: ForgeFixture,
) -> None:
    """A missing GitHub remote cannot block GitLab publication."""

    run("git", "remote", "remove", "github", cwd=forge_fixture["source"])
    published = publish(forge_fixture, "gitlab", "origin")

    assert published == tip(forge_fixture["gitlab"], "main")
    assert run("git", "show-ref", cwd=forge_fixture["github"], check=False).stdout == ""


def test_main_and_dev_advance_atomically_without_rewriting(
    forge_fixture: ForgeFixture,
) -> None:
    """Normal publication is idempotent and forward-only."""

    first = publish(forge_fixture, "gitlab", "origin")
    assert publish(forge_fixture, "gitlab", "origin") == first
    second = signed_commit(forge_fixture["source"], "next.txt", "two\n")
    run("git", "branch", "-f", "dev", second, cwd=forge_fixture["source"])

    assert publish(forge_fixture, "gitlab", "origin") == second
    assert tip(forge_fixture["gitlab"], "main") == tip(forge_fixture["gitlab"], "dev") == second
    run("git", "merge-base", "--is-ancestor", first, second, cwd=forge_fixture["source"])


def test_divergent_peer_fails_without_partial_ref_updates(
    forge_fixture: ForgeFixture,
) -> None:
    """Git fast-forward and atomic semantics guard normal publication."""

    publish(forge_fixture, "gitlab", "origin")
    with tempfile.TemporaryDirectory() as directory:
        checkout = Path(directory) / "checkout"
        run(
            "git",
            "clone",
            "-q",
            str(forge_fixture["gitlab"]),
            str(checkout),
            cwd=Path(directory),
        )
        run("git", "checkout", "-qB", "main", "origin/main", cwd=checkout)
        run("git", "config", "user.name", "Rogue", cwd=checkout)
        run("git", "config", "user.email", "rogue@example.test", cwd=checkout)
        (checkout / "rogue.txt").write_text("rogue\n", encoding="utf-8")
        run("git", "add", "rogue.txt", cwd=checkout)
        run("git", "commit", "-qm", "rogue", cwd=checkout)
        run("git", "push", "-q", "--force", "origin", "HEAD:main", cwd=checkout)
    observed_main = tip(forge_fixture["gitlab"], "main")
    observed_dev = tip(forge_fixture["gitlab"], "dev")
    local = signed_commit(forge_fixture["source"], "local.txt", "local\n")
    run("git", "branch", "-f", "dev", local, cwd=forge_fixture["source"])

    with pytest.raises(ProjectionError, match="exact expected tip is required"):
        publish(forge_fixture, "gitlab", "origin")

    assert tip(forge_fixture["gitlab"], "main") == observed_main
    assert tip(forge_fixture["gitlab"], "dev") == observed_dev


def test_proposal_publication_does_not_touch_persistent_branches(
    forge_fixture: ForgeFixture,
) -> None:
    """A proposal is the only independently publishable non-persistent branch."""

    run("git", "branch", "proposal/review", "main", cwd=forge_fixture["source"])
    published = publish(forge_fixture, "github", "github", "proposal/review")

    assert tip(forge_fixture["github"], "proposal/review") == published
    assert (
        run(
            "git",
            "show-ref",
            "--verify",
            "refs/heads/main",
            cwd=forge_fixture["github"],
            check=False,
        ).returncode
        != 0
    )


def test_projection_requires_clean_trusted_local_identity(
    forge_fixture: ForgeFixture,
) -> None:
    """The projector verifies, but never recreates, the local object."""

    (forge_fixture["source"] / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ProjectionError, match="dirty checkout"):
        publish(forge_fixture, "gitlab", "origin")
    (forge_fixture["source"] / "dirty.txt").unlink()

    with pytest.raises(ProjectionError, match="author and committer email"):
        project(
            root=forge_fixture["source"],
            provider="gitlab",
            source_ref="main",
            remote="origin",
            email="other@example.test",
            allowed_signers=forge_fixture["anchor"],
        )
    other = forge_fixture["source"].parent / "other-signers"
    other.write_text("other ssh-ed25519 AAAA\n", encoding="ascii")
    with pytest.raises(ProjectionError, match="trusted signature"):
        project(
            root=forge_fixture["source"],
            provider="gitlab",
            source_ref="main",
            remote="origin",
            email=forge_fixture["email"],
            allowed_signers=other,
        )


@pytest.mark.parametrize("source_ref", ["dev", "candidate/dev", "work/change", "feature/free"])
def test_projection_rejects_non_publication_branches(
    forge_fixture: ForgeFixture, source_ref: str
) -> None:
    """Only main and proposal refs belong to a Forge peer."""

    if source_ref != "dev":
        run("git", "branch", source_ref, "main", cwd=forge_fixture["source"])
    with pytest.raises(ProjectionError, match="main or proposal"):
        publish(forge_fixture, "gitlab", "origin", source_ref)
