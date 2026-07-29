"""Source-side released deployment orchestration and public mutation boundary."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_adapters import common, deployment, payload, publication
import install
from tests.support.repository_fixtures import install_context


class FakeTransaction:
    """Small behavioral double for the payload-owned transaction protocol."""

    def __init__(self, *, release: str = "1.2.3") -> None:
        self.release = release
        self.expected = {
            "transaction_id": "txn-release",
            "release": release,
            "manifest_sha256": "b" * 64,
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "d" * 64,
        }
        self.events: list[object] = []

    def commit_projection(self) -> None:
        self.events.append("commit")

    def finalize(self, runtime: dict[str, object] | None = None) -> None:
        self.events.append(("finalize", runtime))

    def rollback(self) -> None:
        self.events.append("rollback")

    def preserve_for_recovery(self, reason: str) -> None:
        self.events.append(("preserve", reason))


def as_transaction(value: FakeTransaction) -> "payload.PayloadTransaction":
    """Present the behavioral double through the production transaction protocol."""

    return cast("payload.PayloadTransaction", value)


class TestReleasedDeployment(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = install_context(Path(tempfile.mkdtemp()))

    def test_fresh_install_commits_once_then_finalizes_only_after_service_proof(self) -> None:
        transaction = FakeTransaction()
        runtime = {
            "pid": 123,
            "release": "1.2.3",
            "serving_payload_sha256": "c" * 64,
            "payload_manifest_sha256": "b" * 64,
            "release_receipt_sha256": "d" * 64,
            "accepting": True,
        }
        adapter = mock.Mock()
        with mock.patch.object(deployment, "wait_for_serving_runtime", return_value=runtime):
            result = deployment.install(
                self.ctx,
                as_transaction(transaction),
                adapter=adapter,
                runtime_reader=lambda _ctx: None,
            )
        self.assertEqual(transaction.events, ["commit", ("finalize", runtime)])
        adapter.install.assert_called_once_with(self.ctx)
        self.assertEqual(result["mode"], "fresh-install")

    def test_protocol_v2_upgrade_uses_source_side_handoff_and_never_installed_control(self) -> None:
        transaction = FakeTransaction()
        current: dict[str, object] = {
            "pid": 111,
            "handoff_protocol_version": 2,
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "release": "1.2.2",
            "serving_payload_sha256": "1" * 64,
            "payload_manifest_sha256": "2" * 64,
            "release_receipt_sha256": "3" * 64,
            "accepting": True,
            "draining": False,
        }
        successor = {
            "pid": 222,
            "release": "1.2.3",
            "serving_payload_sha256": "c" * 64,
            "payload_manifest_sha256": "b" * 64,
            "release_receipt_sha256": "d" * 64,
            "accepting": True,
        }
        with (
            mock.patch.object(deployment, "request_handoff", return_value=successor) as handoff,
            mock.patch.object(
                deployment, "load_installed_control", create=True
            ) as installed_control,
        ):
            result = deployment.install(
                self.ctx,
                as_transaction(transaction),
                adapter=mock.Mock(),
                runtime_reader=lambda _ctx: current,
            )
        installed_control.assert_not_called()
        handoff.assert_called_once()
        self.assertEqual(transaction.events, ["commit", ("finalize", successor)])
        self.assertEqual(result["mode"], "protocol-v2-upgrade")

    def test_legacy_upgrade_refuses_before_commit_without_explicit_authorization(self) -> None:
        transaction = FakeTransaction()
        current: dict[str, object] = {
            "pid": 111,
            "release": "1.2.2",
            "active_responses": 0,
        }
        with self.assertRaisesRegex(common.InstallError, "authorized legacy bootstrap"):
            deployment.install(
                self.ctx,
                as_transaction(transaction),
                adapter=mock.Mock(),
                runtime_reader=lambda _ctx: current,
            )
        self.assertEqual(transaction.events, [])

    def test_legacy_upgrade_commits_only_after_source_side_quiet_window(self) -> None:
        transaction = FakeTransaction()
        current: dict[str, object] = {
            "pid": 111,
            "release": "1.2.2",
            "active_responses": 0,
        }
        successor = {
            "pid": 222,
            "release": "1.2.3",
            "serving_payload_sha256": "c" * 64,
            "payload_manifest_sha256": "b" * 64,
            "release_receipt_sha256": "d" * 64,
            "accepting": True,
        }
        with (
            mock.patch.object(deployment, "prove_legacy_quiet_window", return_value=111) as quiet,
            mock.patch.object(deployment, "wait_for_serving_runtime", return_value=successor),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = deployment.install(
                self.ctx,
                as_transaction(transaction),
                adapter=mock.Mock(),
                runtime_reader=lambda _ctx: current,
                allow_legacy_bootstrap=True,
            )
        quiet.assert_called_once()
        terminate.assert_called_once_with(111)
        self.assertEqual(transaction.events, ["commit", ("finalize", successor)])
        self.assertEqual(result["mode"], "legacy-bootstrap")

    def test_unknown_handoff_outcome_preserves_transaction_instead_of_rolling_back(self) -> None:
        transaction = FakeTransaction()
        current: dict[str, object] = {
            "pid": 111,
            "handoff_protocol_version": 2,
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "release": "1.2.2",
            "serving_payload_sha256": "1" * 64,
            "payload_manifest_sha256": "2" * 64,
            "release_receipt_sha256": "3" * 64,
            "accepting": True,
            "draining": False,
        }
        with (
            mock.patch.object(
                deployment,
                "request_handoff",
                side_effect=deployment.UnknownDeploymentOutcome("handoff outcome is unconfirmed"),
            ),
            self.assertRaisesRegex(deployment.UnknownDeploymentOutcome, "unconfirmed"),
        ):
            deployment.install(
                self.ctx,
                as_transaction(transaction),
                adapter=mock.Mock(),
                runtime_reader=lambda _ctx: current,
            )
        self.assertEqual(
            transaction.events,
            ["commit", ("preserve", "handoff outcome is unconfirmed")],
        )


class TestInstallComposition(unittest.TestCase):
    """Keep admission, transaction, and deployment on one source-side entry."""

    def test_install_release_verifies_live_publication_before_source_admission(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        authority = mock.create_autospec(publication.PublishedRelease, instance=True)
        released = mock.Mock()
        tx = mock.Mock()
        with (
            mock.patch.object(install.publication, "verify", return_value=authority) as verify,
            mock.patch.object(install, "admit_released_payload", return_value=released) as admit,
            mock.patch.object(install.payload, "begin_transaction", return_value=tx) as begin,
            mock.patch.object(
                install.deployment, "install", return_value={"mode": "fresh-install"}
            ) as deploy,
        ):
            result = install.install_release(
                ctx,
                tag="v1.2.3",
                gitlab_remote="gitlab-origin",
                gitlab_api_base="https://gitlab.example/api/v4",
                gitlab_repo="group/project",
                github_remote="github-origin",
                github_repo="owner/project",
                gitlab_anchor=Path("/external/gitlab-signers"),
                github_anchor=Path("/external/github-signers"),
                policy=Path("/external/publication-policy.toml"),
                trust_anchor=Path("/external/allowed-signers"),
                adapter=mock.Mock(),
            )
        verify.assert_called_once()
        admit.assert_called_once_with(authority, trust_anchor=Path("/external/allowed-signers"))
        begin.assert_called_once_with(ctx, released)
        deploy.assert_called_once()
        self.assertEqual(result["mode"], "fresh-install")

    def test_publication_verification_failure_refuses_before_source_admission(self) -> None:
        with (
            mock.patch.object(
                install.publication,
                "verify",
                side_effect=publication.PublicationError("GitHub release is unavailable"),
            ),
            mock.patch.object(install.release_source, "admit") as admit,
            self.assertRaisesRegex(publication.PublicationError, "GitHub release"),
        ):
            install.install_release(
                install_context(Path(tempfile.mkdtemp())),
                tag="v1.2.3",
                gitlab_remote="gitlab-origin",
                gitlab_api_base="https://gitlab.example/api/v4",
                gitlab_repo="group/project",
                github_remote="github-origin",
                github_repo="owner/project",
                gitlab_anchor=Path("/external/gitlab-signers"),
                github_anchor=Path("/external/github-signers"),
                policy=Path("/external/publication-policy.toml"),
                trust_anchor=Path("/external/allowed-signers"),
                adapter=mock.Mock(),
            )
        admit.assert_not_called()

    def test_install_has_no_json_publication_proof_loader(self) -> None:
        self.assertFalse(hasattr(install, "publication_proof_from_file"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
