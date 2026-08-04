"""Offline contracts for provider-specific, forward-only Forge projection."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from typing import Iterator, TypedDict

ROOT = Path(__file__).resolve().parents[2]


class ForgeFixture(TypedDict):
    """Typed paths and identities for one isolated projection fixture."""

    source: Path
    gitlab_remote: Path
    github_remote: Path
    gitlab_key: Path
    github_key: Path
    gitlab_anchor: Path
    github_anchor: Path
    context: Path
    gitlab_email: str
    github_email: str


def run(*args: str, cwd: Path, env: dict[str, str] | None = None, check: bool = True):
    """Run one fixture command with isolated Git configuration."""

    environment = os.environ.copy()
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    if env:
        environment.update(env)
    return subprocess.run(
        args, cwd=cwd, env=environment, text=True, capture_output=True, check=check
    )


def fingerprint(public_key: Path, *, cwd: Path) -> str:
    """Return the OpenSSH SHA-256 fingerprint for one public key."""

    return run("ssh-keygen", "-lf", str(public_key), "-E", "sha256", cwd=cwd).stdout.split()[1]


@contextmanager
def ssh_agent(root: Path, *keys: Path) -> Iterator[dict[str, str]]:
    """Yield an isolated agent containing exactly the requested fixture keys."""

    start = run("ssh-agent", "-s", cwd=root).stdout
    environment: dict[str, str] = {}
    for name in ("SSH_AUTH_SOCK", "SSH_AGENT_PID"):
        match = re.search(rf"{name}=([^;]+)", start)
        if match is None:
            raise RuntimeError(f"ssh-agent omitted {name}")
        environment[name] = match.group(1)
    try:
        run("ssh-add", *(str(key) for key in keys), cwd=root, env=environment)
        yield environment
    finally:
        run("ssh-agent", "-k", cwd=root, env=environment, check=False)


class ProviderProjectionTests:
    """Prove separate Forge identities over one ordered source-tree history."""

    def setup_method(self) -> None:
        for executable in ("ssh-agent", "ssh-add", "ssh-keygen"):
            if shutil.which(executable) is None:
                pytest.skip(f"{executable} is required")

    def fixture(self, root: Path) -> ForgeFixture:
        """Create a GitLab-authored source, two remotes, identities, and trust."""

        source = root / "source"
        gitlab_remote = root / "gitlab.git"
        github_remote = root / "github.git"
        gitlab_key = root / "gitlab-signing"
        github_key = root / "github-signing"
        gitlab_anchor = root / "gitlab-allowed-signers"
        github_anchor = root / "github-allowed-signers"
        context = root / "publication-context.toml"
        gitlab_email = "gitlab-publisher@example.test"
        github_email = "github-publisher@example.test"

        for key in (gitlab_key, github_key):
            run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), cwd=root)
        gitlab_public = " ".join(gitlab_key.with_suffix(".pub").read_text().split()[:2])
        github_public = " ".join(github_key.with_suffix(".pub").read_text().split()[:2])
        gitlab_anchor.write_text(
            f'{gitlab_email} namespaces="git" {gitlab_public}\n', encoding="utf-8"
        )
        github_anchor.write_text(
            f'{github_email} namespaces="git" {github_public}\n', encoding="utf-8"
        )
        context.write_text(
            "schema-version = 1\n\n"
            '[gitlab]\nactor-name = "GitLab Publisher"\n'
            f'actor-email = "{gitlab_email}"\n'
            f'active-signing-fingerprint = "{fingerprint(gitlab_key.with_suffix(".pub"), cwd=root)}"\n\n'
            '[github]\nactor-name = "GitHub Publisher"\n'
            f'actor-email = "{github_email}"\n'
            f'active-signing-fingerprint = "{fingerprint(github_key.with_suffix(".pub"), cwd=root)}"\n',
            encoding="utf-8",
        )

        run("git", "init", "-q", "--bare", str(gitlab_remote), cwd=root)
        run("git", "init", "-q", "--bare", str(github_remote), cwd=root)
        run("git", "init", "-q", "-b", "dev", str(source), cwd=root)
        run("git", "config", "core.hooksPath", os.devnull, cwd=source)
        run("git", "config", "user.name", "GitLab Publisher", cwd=source)
        run("git", "config", "user.email", gitlab_email, cwd=source)
        run("git", "config", "user.useConfigOnly", "true", cwd=source)
        run("git", "config", "gpg.format", "ssh", cwd=source)
        run("git", "config", "gpg.ssh.program", "ssh-keygen", cwd=source)
        run("git", "config", "user.signingkey", str(gitlab_key), cwd=source)
        (source / "README.md").write_text("one\n", encoding="utf-8")
        (source / "tools" / "forge").mkdir(parents=True)
        for name in ("context.sh", "history.py", "project.sh"):
            source_file = ROOT / "tools" / "forge" / name
            if source_file.exists():
                shutil.copy2(source_file, source / "tools" / "forge")
        run("git", "add", ".", cwd=source)
        run("git", "commit", "-qS", "-m", "publication contract", cwd=source)
        (source / "CONTRIBUTING.md").write_text("two\n", encoding="utf-8")
        run("git", "add", ".", cwd=source)
        run("git", "commit", "-qS", "-m", "team contribution", cwd=source)
        run("git", "remote", "add", "origin", str(gitlab_remote), cwd=source)
        run("git", "remote", "add", "github", str(github_remote), cwd=source)
        return {
            "source": source,
            "gitlab_remote": gitlab_remote,
            "github_remote": github_remote,
            "gitlab_key": gitlab_key,
            "github_key": github_key,
            "gitlab_anchor": gitlab_anchor,
            "github_anchor": github_anchor,
            "context": context,
            "gitlab_email": gitlab_email,
            "github_email": github_email,
        }

    @staticmethod
    def environment(fixture: ForgeFixture, agent: dict[str, str]) -> dict[str, str]:
        """Return the complete external publication context for one fixture."""

        return {
            **agent,
            "PYTHON": sys.executable,
            "CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT": str(fixture["context"]),
            "CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS": str(fixture["gitlab_anchor"]),
            "CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS": str(fixture["github_anchor"]),
        }

    def test_each_forge_uses_its_identity_and_preserves_the_source_tree(self) -> None:
        """Keep GitLab canonical while GitHub gets a signed identity projection."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            source_head = run("git", "rev-parse", "HEAD", cwd=source).stdout.strip()
            source_tree = run("git", "rev-parse", "HEAD^{tree}", cwd=source).stdout.strip()
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                environment = self.environment(fixture, agent)
                for provider in ("gitlab", "github"):
                    mapping = root / f"{provider}-mapping.json"
                    result = run(
                        "sh",
                        "tools/forge/project.sh",
                        "--provider",
                        provider,
                        "--source-ref",
                        "HEAD",
                        "--map-output",
                        str(mapping),
                        cwd=source,
                        env=environment,
                    )
                    assert "Traceback" not in result.stderr
                    projection = json.loads(mapping.read_text(encoding="utf-8"))
                    remote = (
                        fixture["gitlab_remote"]
                        if provider == "gitlab"
                        else fixture["github_remote"]
                    )
                    remote_head = run(
                        "git", "rev-parse", "refs/heads/main", cwd=remote
                    ).stdout.strip()
                    remote_tree = run(
                        "git", "rev-parse", "refs/heads/main^{tree}", cwd=remote
                    ).stdout.strip()
                    assert source_tree == remote_tree
                    assert remote_head == projection["projected_commit"]
                    assert source_head == projection["source_commit"]
                    assert source_tree == projection["tree"]
                    if provider == "gitlab":
                        assert source_head == remote_head
                    else:
                        assert source_head != remote_head
                    emails = run(
                        "git", "log", "--format=%ae%n%ce", "main", cwd=remote
                    ).stdout.splitlines()
                    expected_email = (
                        fixture["gitlab_email"] if provider == "gitlab" else fixture["github_email"]
                    )
                    commit_anchor = (
                        fixture["gitlab_anchor"]
                        if provider == "gitlab"
                        else fixture["github_anchor"]
                    )
                    assert {expected_email} == set(emails)
                    for commit in run("git", "rev-list", "main", cwd=remote).stdout.splitlines():
                        run(
                            "git",
                            "-c",
                            "gpg.format=ssh",
                            "-c",
                            "gpg.ssh.program=ssh-keygen",
                            "-c",
                            f"gpg.ssh.allowedSignersFile={commit_anchor}",
                            "verify-commit",
                            commit,
                            cwd=remote,
                        )

    def test_github_projection_appends_without_rewriting_existing_projection(self) -> None:
        """Append a new canonical tree while retaining the old GitHub tip."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            github_remote = fixture["github_remote"]
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                environment = self.environment(fixture, agent)
                run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "github",
                    cwd=source,
                    env=environment,
                )
                old_tip = run(
                    "git", "rev-parse", "refs/heads/main", cwd=github_remote
                ).stdout.strip()
                (source / "CHANGELOG.md").write_text("three\n", encoding="utf-8")
                run("git", "add", ".", cwd=source)
                run("git", "commit", "-qS", "-m", "next source tree", cwd=source)
                mapping = root / "incremental-map.json"
                run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "github",
                    "--map-output",
                    str(mapping),
                    cwd=source,
                    env=environment,
                )
                new_tip = run(
                    "git", "rev-parse", "refs/heads/main", cwd=github_remote
                ).stdout.strip()
                run("git", "merge-base", "--is-ancestor", old_tip, new_tip, cwd=github_remote)
                assert (
                    run("git", "rev-parse", "HEAD^{tree}", cwd=source).stdout.strip()
                    == run("git", "rev-parse", "main^{tree}", cwd=github_remote).stdout.strip()
                )
                projection = json.loads(mapping.read_text(encoding="utf-8"))
                assert old_tip == projection["base_projected_commit"]
                assert 1 == len(projection["created"])

    def test_incremental_projection_fingerprints_each_history_commit_once(self) -> None:
        """Keep incremental history matching linear in both commit histories."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            github_remote = fixture["github_remote"]
            for index in range(6):
                (source / f"history-{index}.txt").write_text(f"{index}\n", encoding="utf-8")
                run("git", "add", ".", cwd=source)
                run("git", "commit", "-qS", "-m", f"history {index}", cwd=source)
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                environment = self.environment(fixture, agent)
                run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "github",
                    cwd=source,
                    env=environment,
                )
                old_tip = run(
                    "git", "rev-parse", "refs/heads/main", cwd=github_remote
                ).stdout.strip()
                (source / "successor.txt").write_text("successor\n", encoding="utf-8")
                run("git", "add", ".", cwd=source)
                run("git", "commit", "-qS", "-m", "one successor", cwd=source)

                trace_log = root / "git-trace2.jsonl"
                mapping = root / "linear-map.json"
                result = run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "github",
                    "--map-output",
                    str(mapping),
                    cwd=source,
                    env={
                        **environment,
                        "GIT_TRACE2_EVENT": str(trace_log),
                    },
                )

            assert "Traceback" not in result.stderr
            starts = [
                json.loads(line)["argv"]
                for line in trace_log.read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("event") == "start"
            ]
            message_reads = sum("cat-file" in command and "commit" in command for command in starts)
            batch_reads = sum("cat-file" in command and "--batch" in command for command in starts)
            assert 2 == batch_reads
            projection = json.loads(mapping.read_text(encoding="utf-8"))
            assert 1 == len(projection["created"])
            assert len(projection["created"]) == message_reads
            new_tip = run("git", "rev-parse", "refs/heads/main", cwd=github_remote).stdout.strip()
            run("git", "merge-base", "--is-ancestor", old_tip, new_tip, cwd=github_remote)

    def test_untrusted_canonical_commit_is_rejected_without_ref_change(self) -> None:
        """Reject source history outside canonical GitLab identity and trust."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            gitlab_remote = fixture["gitlab_remote"]
            outsider = root / "outsider-signing"
            run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(outsider), cwd=root)
            run("git", "config", "user.email", "untrusted@example.test", cwd=source)
            run("git", "config", "user.signingkey", str(outsider), cwd=source)
            (source / "UNTRUSTED.md").write_text("three\n", encoding="utf-8")
            run("git", "add", ".", cwd=source)
            run("git", "commit", "-qS", "-m", "untrusted contribution", cwd=source)
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                result = run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "gitlab",
                    cwd=source,
                    check=False,
                    env=self.environment(fixture, agent),
                )
            assert 0 != result.returncode
            assert "canonical GitLab identity" in result.stderr
            assert (
                ""
                == run(
                    "git",
                    "for-each-ref",
                    "refs/heads/main",
                    "--format=%(objectname)",
                    cwd=gitlab_remote,
                ).stdout.strip()
            )

    def test_divergent_github_tree_is_rejected_without_ref_change(self) -> None:
        """Refuse a remote tree absent from canonical source history."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            github_remote = fixture["github_remote"]
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                environment = self.environment(fixture, agent)
                run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "github",
                    cwd=source,
                    env=environment,
                )
                divergent = root / "divergent"
                run("git", "clone", "-q", str(github_remote), str(divergent), cwd=root)
                run("git", "checkout", "-qb", "main", "origin/main", cwd=divergent)
                run("git", "config", "user.name", "GitHub Publisher", cwd=divergent)
                run("git", "config", "user.email", str(fixture["github_email"]), cwd=divergent)
                run("git", "config", "gpg.format", "ssh", cwd=divergent)
                run("git", "config", "user.signingkey", str(fixture["github_key"]), cwd=divergent)
                (divergent / "REMOTE_ONLY.md").write_text("divergent\n", encoding="utf-8")
                run("git", "add", ".", cwd=divergent)
                run("git", "commit", "-qS", "-m", "remote-only tree", cwd=divergent)
                run("git", "push", "-q", "origin", "HEAD:main", cwd=divergent)
                before = run(
                    "git", "rev-parse", "refs/heads/main", cwd=github_remote
                ).stdout.strip()
                result = run(
                    "sh",
                    "tools/forge/project.sh",
                    "--provider",
                    "github",
                    cwd=source,
                    check=False,
                    env=environment,
                )
            assert 0 != result.returncode
            assert "tree diverges from canonical history" in result.stderr
            assert (
                before
                == run("git", "rev-parse", "refs/heads/main", cwd=github_remote).stdout.strip()
            )
