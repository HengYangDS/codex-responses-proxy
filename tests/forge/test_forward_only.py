"""Exact local-object publication contracts for optional Forge peers."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest

from tools.forge import project as projector
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


def test_main_publication_batches_peer_observation_and_skips_noop_push(
    forge_fixture: ForgeFixture, mocker
) -> None:
    """One peer snapshot and fetch cover both protected refs per publication."""
    publish(forge_fixture, "gitlab", "origin")
    next_commit = signed_commit(forge_fixture["source"], "next.txt", "two\n")
    run("git", "branch", "-f", "dev", next_commit, cwd=forge_fixture["source"])
    git = mocker.spy(projector, "_git")

    assert publish(forge_fixture, "gitlab", "origin") == next_commit
    observations = [call.args for call in git.call_args_list if call.args[1] == "ls-remote"]
    assert len(observations) == 2
    assert all({"refs/heads/main", "refs/heads/dev"} <= set(call) for call in observations)
    assert sum(call.args[1] == "fetch" for call in git.call_args_list) == 1
    assert sum(call.args[1] == "push" for call in git.call_args_list) == 1

    git.reset_mock()
    assert publish(forge_fixture, "gitlab", "origin") == next_commit
    assert sum(call.args[1] == "ls-remote" for call in git.call_args_list) == 1
    assert not any(call.args[1] in {"fetch", "push"} for call in git.call_args_list)


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


@pytest.mark.parametrize(
    "failure", [OSError("missing"), subprocess.CompletedProcess([], 2, "", "failed")]
)
def test_git_failure_is_not_interpreted_as_remote_absence(tmp_path, failure, mocker):
    if isinstance(failure, OSError):
        mocker.patch.object(projector.subprocess, "run", side_effect=failure)
    else:
        mocker.patch.object(projector.subprocess, "run", return_value=failure)
    with pytest.raises(ProjectionError):
        projector._git(tmp_path, "ls-remote")


@pytest.mark.parametrize("value", ["", "main", "=abc", "main=", "main=a", "main=b"])
def test_expected_tips_require_unique_branch_values(value):
    if value in {"main=a", "main=b"}:
        assert projector._parse_expected((value,)) == {"main": value.partition("=")[2]}
        with pytest.raises(ProjectionError, match="unique"):
            projector._parse_expected((value, value))
    else:
        with pytest.raises(ProjectionError, match="unique"):
            projector._parse_expected((value,))


def test_observation_and_ancestry_failures_remain_errors(tmp_path, mocker):
    output = mocker.patch.object(projector, "_output", return_value="a refs/heads/wrong")
    with pytest.raises(ProjectionError, match="malformed"):
        projector._remote_tips(tmp_path, "peer", ("main",))
    output.return_value = "a refs/heads/main\nb refs/heads/main"
    with pytest.raises(ProjectionError, match="malformed"):
        projector._remote_tips(tmp_path, "peer", ("main",))
    output.return_value = "refs/tags/main"
    with pytest.raises(ProjectionError, match="not a local branch"):
        projector._local_branch(tmp_path, "main")
    mocker.patch.object(
        projector, "_git", return_value=subprocess.CompletedProcess([], 2, "", "failed")
    )
    with pytest.raises(ProjectionError, match="failed"):
        projector._is_ancestor(tmp_path, "a", "b")
    with pytest.raises(ProjectionError, match="trust anchor"):
        projector._verify_local_identity(tmp_path, "a", "author", tmp_path / "absent")


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_selected_runner_admission_precedes_ref_publication(provider, tmp_path, mocker):
    mocker.patch.object(projector, "_output", return_value="")
    mocker.patch.object(projector, "_local_branch", return_value=("refs/heads/main", "a" * 40))
    mocker.patch.object(projector, "_verify_local_identity")
    tips = mocker.patch.object(
        projector, "_remote_tips", return_value={"main": "a" * 40, "dev": "a" * 40}
    )
    git = mocker.patch.object(projector, "_git")
    admission = mocker.patch.object(projector.runner_admission, f"_{provider}")
    assert (
        projector.project(
            root=tmp_path,
            provider=provider,
            source_ref="main",
            remote="peer",
            email="author",
            allowed_signers=tmp_path / "anchor",
            repository_coordinate="team/repo",
        )
        == "a" * 40
    )
    assert admission.call_count == 1
    assert tips.call_count == 1
    git.assert_not_called()


@pytest.mark.parametrize("cutover", [False, True])
def test_divergent_cutover_and_post_push_readback_are_exact(cutover, tmp_path, mocker):
    mocker.patch.object(projector, "_output", return_value="")
    mocker.patch.object(projector, "_local_branch", return_value=("refs/heads/main", "a" * 40))
    mocker.patch.object(projector, "_verify_local_identity")
    mocker.patch.object(
        projector,
        "_remote_tips",
        side_effect=[
            {"main": "b" * 40, "dev": "b" * 40},
            {"main": "c" * 40, "dev": "c" * 40},
        ],
    )
    mocker.patch.object(projector, "_fetch_remote_branches")
    mocker.patch.object(projector, "_is_ancestor", return_value=False)
    git = mocker.patch.object(projector, "_git")
    with pytest.raises(ProjectionError, match="does not equal" if cutover else "diverges"):
        projector.project(
            root=tmp_path,
            provider="github",
            source_ref="main",
            remote="peer",
            email="author",
            allowed_signers=tmp_path / "anchor",
            expected_remote_tips={"main": "b" * 40, "dev": "b" * 40} if cutover else None,
        )
    if cutover:
        assert "--force-with-lease=refs/heads/main:" + "b" * 40 in git.call_args.args
    else:
        git.assert_not_called()


@pytest.mark.parametrize("as_json", [False, True])
def test_projection_cli_preserves_machine_and_human_results(as_json, tmp_path, mocker, capsys):
    import json

    invoke = mocker.patch.object(projector, "project", return_value="a" * 40)
    args = (
        "--provider",
        "github",
        "--email",
        "author",
        "--allowed-signers",
        str(tmp_path / "anchor"),
    )
    projector.main((*args, "--json") if as_json else args)
    output = capsys.readouterr().out
    if as_json:
        assert json.loads(output)["commit"] == "a" * 40
    else:
        assert "github synchronized" in output
    invoke.side_effect = ProjectionError("rejected")
    with pytest.raises(SystemExit) as stopped:
        projector.main(args)
    assert stopped.value.code == 1
    assert "rejected" in capsys.readouterr().err


def test_unknown_forge_never_starts_a_git_operation(tmp_path, mocker):
    git = mocker.patch.object(projector, "_git")
    with pytest.raises(ProjectionError, match="provider must"):
        projector.project(
            root=tmp_path,
            provider="unknown",
            source_ref="main",
            remote="peer",
            email="author",
            allowed_signers=tmp_path / "anchor",
        )
    git.assert_not_called()
