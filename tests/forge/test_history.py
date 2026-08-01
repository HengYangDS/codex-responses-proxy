#!/usr/bin/env python3
"""Git history fingerprint and unique-join contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.forge import history


class HistoryIndexTests(unittest.TestCase):
    """Keep Forge history matching exact, bounded, and provider-neutral."""

    def test_index_matches_the_original_git_fingerprint_contract(self) -> None:
        """Match an independent Git oracle for every commit shape."""

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            subprocess.run(["git", "init", "-q", "-b", "main", repository], check=True)
            subprocess.run(
                ["git", "-C", repository, "config", "core.hooksPath", os.devnull], check=True
            )
            subprocess.run(
                ["git", "-C", repository, "config", "user.name", "History Test"], check=True
            )
            subprocess.run(
                ["git", "-C", repository, "config", "user.email", "history@example.test"],
                check=True,
            )
            (repository / "README.md").write_text("history\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repository, "commit", "-qm", "root message"],
                check=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_DATE": "1970-01-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "1970-01-01T00:00:00+0000",
                },
            )
            subprocess.run(["git", "-C", repository, "checkout", "-qb", "side"], check=True)
            (repository / "side.txt").write_text("side\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(["git", "-C", repository, "commit", "-qm", "side message"], check=True)
            subprocess.run(["git", "-C", repository, "checkout", "-q", "main"], check=True)
            (repository / "main.txt").write_text("main\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(["git", "-C", repository, "commit", "-qm", "main message"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    repository,
                    "merge",
                    "-q",
                    "--no-ff",
                    "side",
                    "-m",
                    "merge message\n\nwith body",
                ],
                check=True,
            )
            commits = subprocess.check_output(
                ["git", "-C", repository, "rev-list", "--reverse", "HEAD"], text=True
            ).splitlines()
            expected = [(self.git_fingerprint(repository, commit), commit) for commit in commits]

            self.assertEqual(expected, history.build_index(repository, commits))

            canonical = Path(directory) / "canonical.txt"
            projected = Path(directory) / "projected.txt"
            output = Path(directory) / "mapping.tsv"
            canonical.write_text("".join(f"{commit}\n" for commit in commits), encoding="utf-8")
            projected.write_text("".join(f"{commit}\n" for commit in commits), encoding="utf-8")
            arguments = [
                "history.py",
                "--repository",
                str(repository),
                "--canonical",
                str(canonical),
                "--projected",
                str(projected),
                "--remote-commit",
                commits[-1],
                "--output",
                str(output),
            ]
            stdout = StringIO()
            with mock.patch.object(sys, "argv", arguments), redirect_stdout(stdout):
                history.main()
            self.assertEqual(commits[-1], stdout.getvalue().strip())
            self.assertEqual(
                "".join(f"{commit}\t{commit}\n" for commit in commits),
                output.read_text(encoding="utf-8"),
            )

    def test_join_requires_one_base_and_one_projection_per_fingerprint(self) -> None:
        """Reject absent or ambiguous matches before returning a mapping."""

        canonical = [("one", "source-1"), ("two", "source-2"), ("three", "source-3")]
        projected = [("one", "target-1"), ("two", "target-2")]
        self.assertEqual(
            ("source-2", [("source-1", "target-1"), ("source-2", "target-2")]),
            history.join_indexes(canonical, projected, "target-2"),
        )
        with self.assertRaisesRegex(history.HistoryError, "found 0"):
            history.join_indexes(canonical, [("other", "target")], "target")
        with self.assertRaisesRegex(history.HistoryError, "found 2"):
            history.join_indexes([*canonical, ("two", "source-4")], projected, "target-2")
        with self.assertRaisesRegex(history.HistoryError, "ambiguous"):
            history.join_indexes(canonical, [*projected, ("one", "target-3")], "target-2")
        with self.assertRaisesRegex(history.HistoryError, "absent"):
            history.join_indexes(canonical, projected, "missing")

    def test_index_cli_rejects_non_commit_without_traceback(self) -> None:
        """Keep corrupt or mistyped history input bounded and diagnostic-only."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            subprocess.run(["git", "init", "-q", "-b", "main", repository], check=True)
            blob = (
                subprocess.check_output(
                    ["git", "-C", repository, "hash-object", "-w", "--stdin"],
                    input=b"not a commit\n",
                )
                .decode("ascii")
                .strip()
            )
            commits = root / "commits.txt"
            projected = root / "projected.txt"
            output = root / "index.tsv"
            commits.write_text(f"{blob}\n", encoding="utf-8")
            projected.write_text(f"{blob}\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "forge" / "history.py"),
                    "--repository",
                    str(repository),
                    "--canonical",
                    str(commits),
                    "--projected",
                    str(projected),
                    "--remote-commit",
                    blob,
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("cannot read commit object", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output.exists())

    def test_batch_index_rejects_unsupported_and_malformed_git_output(self) -> None:
        """Reject every batch framing ambiguity before emitting an index."""

        repository = Path("repository")
        with mock.patch.object(history, "_git_output", return_value="unknown"):
            with self.assertRaisesRegex(history.HistoryError, "unsupported"):
                history.build_index(repository, ["commit"])

        valid_commit = (
            b"tree deadbeef\n"
            b"author Example <x@example.test> 0 +0000\n"
            b"committer Example <x@example.test> 0 +0000\n\nmessage\n"
        )
        cases = (
            (b"commit missing\n", "cannot read"),
            (b"other commit 1\n", "cannot read"),
            (b"commit commit not-a-size\n", "batch size"),
            (b"commit commit -1\n", "batch size"),
            (b"commit commit 1\nx", "malformed"),
            (
                f"commit commit {len(valid_commit)}\n".encode() + valid_commit + b"\ntrailing",
                "trailing",
            ),
        )
        for stdout, message in cases:
            completed = subprocess.CompletedProcess([], 0, stdout=stdout, stderr=b"")
            with (
                self.subTest(stdout=stdout),
                mock.patch.object(history, "_git_output", return_value="sha1"),
                mock.patch.object(history.subprocess, "run", return_value=completed),
                self.assertRaisesRegex(history.HistoryError, message),
            ):
                history.build_index(repository, ["commit"])

    def test_fingerprint_rejects_malformed_commit_bytes(self) -> None:
        """Convert malformed commit internals into the same bounded error type."""

        invalid_objects = (
            b"tree deadbeef\nauthor Example <x@example.test> 0 +0000\n",
            b"tree deadbeef\n\nmessage\n",
            (
                b"tree deadbeef\n"
                b"author Example <x@example.test> not-time +0000\n"
                b"committer Example <x@example.test> 0 +0000\n\nmessage\n"
            ),
        )
        for raw in invalid_objects:
            with self.subTest(raw=raw), self.assertRaises(history.HistoryError):
                history._fingerprint(raw, history.hashlib.sha1)
        self.assertEqual(
            "1969-12-31T19:00:00-05:00",
            history._strict_iso8601(b"Example <x@example.test> 0 -0500"),
        )
        for offset in (b"+0000", b"-0000"):
            with self.subTest(offset=offset):
                self.assertEqual(
                    "1970-01-01T00:00:00Z",
                    history._strict_iso8601(b"Example <x@example.test> 0 " + offset),
                )

    @staticmethod
    def git_fingerprint(repository: Path, commit: str) -> str:
        """Reproduce the retired shell contract without calling production code."""

        parents = subprocess.check_output(
            ["git", "-C", repository, "show", "-s", "--format=%P", commit], text=True
        ).split()
        identity_neutral_headers = subprocess.check_output(
            ["git", "-C", repository, "show", "-s", "--format=%T%n%aI%n%cI", commit]
        )
        raw = subprocess.check_output(["git", "-C", repository, "cat-file", "commit", commit])
        message = raw.split(b"\n\n", 1)[1]
        payload = (
            f"parents={len(parents)}\n".encode()
            + identity_neutral_headers
            + b"---message---\n"
            + message
        )
        return (
            subprocess.check_output(
                ["git", "-C", repository, "hash-object", "--stdin"], input=payload, text=False
            )
            .decode("ascii")
            .strip()
        )


if __name__ == "__main__":
    unittest.main()
