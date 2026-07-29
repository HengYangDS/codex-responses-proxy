#!/usr/bin/env python3
"""Contracts for live dual-Forge provenance and historical tag evidence."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_audit():
    spec = importlib.util.spec_from_file_location(
        "dual_forge_audit", ROOT / "scripts" / "audit-dual-forge-parity.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load dual-Forge audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DualForgeAuditContracts(unittest.TestCase):
    def test_provider_identities_share_one_display_name(self) -> None:
        audit = load_audit()
        self.assertEqual(audit.GITLAB_IDENTITY, ("Yang HENG", "heng.yang.ds@hotmail.com"))
        self.assertEqual(audit.GITHUB_IDENTITY, ("Yang HENG", "hengyang.2003@tsinghua.org.cn"))

    def test_branch_provenance_requires_exact_names_and_emails(self) -> None:
        audit = load_audit()
        with tempfile.TemporaryDirectory() as directory:
            anchor = Path(directory) / "allowed-signers"
            anchor.write_text("anchor\n", encoding="utf-8")
            with (
                mock.patch.object(audit, "output") as output,
                mock.patch.object(audit, "command") as command,
            ):
                output.side_effect = [
                    "commit",
                    "Yang HENG\0gitlab@example\0Yang HENG\0gitlab@example",
                ]
                command.return_value.returncode = 0
                valid = audit.branch_provenance("main", ("Yang HENG", "gitlab@example"), anchor)
                self.assertTrue(valid["identity_only"])
                output.side_effect = [
                    "commit",
                    "Wrong Name\0gitlab@example\0Yang HENG\0gitlab@example",
                ]
                invalid = audit.branch_provenance("main", ("Yang HENG", "gitlab@example"), anchor)
                self.assertFalse(invalid["identity_only"])

    def test_detached_historical_tags_are_retained_with_relation_metadata(self) -> None:
        audit = load_audit()
        commands = []

        def command(*args, **kwargs):
            commands.append(args)
            result = mock.Mock(returncode=1 if "--is-ancestor" in args else 0, stdout="")
            if args[-2:] == ("provider", "v[0-9]*"):
                result.stdout = "a\trefs/tags/v1.0.0\n"
            return result

        with (
            mock.patch.object(audit, "command", side_effect=command),
            mock.patch.object(audit, "remote_url", return_value="remote"),
            mock.patch.object(audit, "output", return_value="tree"),
            mock.patch.object(audit.shutil, "rmtree"),
        ):
            evidence = audit.provider_release_evidence("origin", "gitlab")
        self.assertIn("v1.0.0", evidence)
        self.assertFalse(evidence["v1.0.0"]["reachable_from_main"])
        self.assertTrue(any("--is-ancestor" in args for args in commands))


if __name__ == "__main__":
    unittest.main(verbosity=2)
