"""Source-side released deployment orchestration and public mutation boundary."""

from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import TypedDict, cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.deployment import apply
from codex_dmx_proxy import errors
from codex_dmx_proxy import process
from codex_dmx_proxy.release import publication
from codex_dmx_proxy.release import projection
from codex_dmx_proxy.release import transaction
import install
from tests.support.repository_fixtures import install_context
from tests.support.repository_fixtures import write_retired_projection


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


def as_transaction(value: FakeTransaction) -> "transaction.PayloadTransaction":
    """Present the behavioral double through the production transaction protocol."""

    return cast("transaction.PayloadTransaction", value)


class FakeServiceAdapter:
    """Minimal controllable implementation of the service-adapter protocol."""

    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.install_mock = mock.Mock(side_effect=failure)

    def install(self, ctx) -> None:
        self.install_mock(ctx)


class InstallArguments(TypedDict):
    tag: str
    gitlab_remote: str
    gitlab_api_base: str
    gitlab_repo: str
    github_remote: str
    github_repo: str
    gitlab_anchor: Path
    github_anchor: Path
    policy: Path
    trust_anchor: Path
    adapter: apply.ServiceAdapter


class TestReleasedDeployment(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = install_context(Path(tempfile.mkdtemp()))

    @staticmethod
    def _runtime(**changes: object) -> dict[str, object]:
        runtime: dict[str, object] = {
            "pid": 222,
            "release": "1.2.3",
            "serving_payload_sha256": "c" * 64,
            "payload_manifest_sha256": "b" * 64,
            "release_receipt_sha256": "d" * 64,
            "accepting": True,
        }
        runtime.update(changes)
        return runtime

    def _install(
        self,
        payload: FakeTransaction,
        current: dict[str, object] | None = None,
        *,
        adapter: apply.ServiceAdapter | None = None,
        timeout_seconds: float = 30.0,
        allow_legacy_bootstrap: bool = False,
        force_legacy_bootstrap: bool = False,
    ) -> dict[str, object]:
        return apply.install(
            self.ctx,
            as_transaction(payload),
            adapter=adapter or FakeServiceAdapter(),
            runtime_reader=lambda _ctx: current,
            timeout_seconds=timeout_seconds,
            allow_legacy_bootstrap=allow_legacy_bootstrap,
            force_legacy_bootstrap=force_legacy_bootstrap,
        )

    @staticmethod
    def _legacy_runtime() -> dict[str, object]:
        return {"pid": 111, "release": "1.2.2", "active_responses": 0}

    @staticmethod
    def _protocol_v2_runtime() -> dict[str, object]:
        return {
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

    @staticmethod
    def _legacy_listener() -> apply.LegacyListener:
        script = "/installed/proxy/dmx_responses_proxy.py"
        projection_state = projection.HistoricalProjection(
            "1.0.26", frozenset({"proxy/dmx_responses_proxy.py"}), script
        )
        return apply.LegacyListener(projection_state, process.OwnedProcess(111, script))

    def test_fresh_install_commits_once_then_finalizes_only_after_service_proof(self) -> None:
        transaction = FakeTransaction()
        runtime = self._runtime(pid=123)
        adapter = FakeServiceAdapter()
        with (
            mock.patch.object(process, "listener_pids", return_value=[]),
            mock.patch.object(apply, "wait_for_serving_runtime", return_value=runtime),
        ):
            result = self._install(transaction, adapter=adapter)
        self.assertEqual(transaction.events, ["commit", ("finalize", runtime)])
        adapter.install_mock.assert_called_once_with(self.ctx)
        self.assertEqual(result["mode"], "fresh-install")

    def test_protocol_v2_upgrade_uses_source_side_handoff_and_never_installed_control(self) -> None:
        transaction = FakeTransaction()
        current = self._protocol_v2_runtime()
        successor = self._runtime()
        with (
            mock.patch.object(apply, "request_handoff", return_value=successor) as handoff,
            mock.patch.object(apply, "load_installed_control", create=True) as installed_control,
        ):
            result = self._install(transaction, current)
        installed_control.assert_not_called()
        handoff.assert_called_once()
        self.assertEqual(transaction.events, ["commit", ("finalize", successor)])
        self.assertEqual(result["mode"], "protocol-v2-upgrade")

    def test_legacy_or_unreadable_listener_refuses_before_commit_without_authorization(
        self,
    ) -> None:
        for current, listeners in ((self._legacy_runtime(), []), (None, [111])):
            with self.subTest(current=current):
                payload = FakeTransaction()
                with (
                    mock.patch.object(
                        process, "verified_proxy_listener_pids", return_value=listeners
                    ),
                    self.assertRaisesRegex(errors.InstallError, "authorized legacy bootstrap"),
                ):
                    self._install(payload, current)
                self.assertEqual(payload.events, [])

    def test_legacy_upgrade_commits_only_after_source_side_quiet_window(self) -> None:
        transaction = FakeTransaction()
        current = self._legacy_runtime()
        successor = self._runtime()
        adapter = FakeServiceAdapter()
        with (
            mock.patch.object(
                apply,
                "prove_legacy_quiet_window",
                return_value=self._legacy_listener(),
            ) as quiet,
            mock.patch.object(apply, "wait_for_serving_runtime", return_value=successor),
            mock.patch.object(process, "terminate_pid", return_value=True) as terminate,
        ):
            result = self._install(
                transaction, current, adapter=adapter, allow_legacy_bootstrap=True
            )
        quiet.assert_called_once()
        terminate.assert_called_once_with(
            111, expected_path="/installed/proxy/dmx_responses_proxy.py"
        )
        adapter.install_mock.assert_called_once_with(self.ctx)
        self.assertEqual(transaction.events, ["commit", ("finalize", successor)])
        self.assertEqual(result["mode"], "legacy-bootstrap")

    def test_unknown_handoff_outcome_preserves_transaction_instead_of_rolling_back(self) -> None:
        transaction = FakeTransaction()
        current = self._protocol_v2_runtime()
        with (
            mock.patch.object(
                apply,
                "request_handoff",
                side_effect=apply.UnknownDeploymentOutcome("handoff outcome is unconfirmed"),
            ),
            self.assertRaisesRegex(apply.UnknownDeploymentOutcome, "unconfirmed"),
        ):
            self._install(transaction, current)
        self.assertEqual(
            transaction.events,
            ["commit", ("preserve", "handoff outcome is unconfirmed")],
        )

    def test_fresh_install_rolls_back_after_service_or_runtime_proof_failure(self) -> None:
        failures = RuntimeError("service failed"), errors.InstallError("runtime timeout")
        for service_fails, failure in enumerate(failures, start=1):
            with self.subTest(failure=failure):
                payload = FakeTransaction()
                adapter = FakeServiceAdapter(failure=failure if service_fails == 1 else None)
                with (
                    mock.patch.object(process, "listener_pids", return_value=[]),
                    mock.patch.object(
                        apply,
                        "wait_for_serving_runtime",
                        side_effect=None if service_fails == 1 else failure,
                    ),
                    self.assertRaises(type(failure)),
                ):
                    self._install(payload, adapter=adapter)
                self.assertEqual(payload.events, ["commit", "rollback"])

    def test_protocol_v2_failure_rolls_back_when_the_outcome_is_proven_rolled_back(self) -> None:
        payload = FakeTransaction()
        current = self._protocol_v2_runtime()
        with (
            mock.patch.object(
                apply,
                "request_handoff",
                side_effect=errors.InstallError("handoff rolled back"),
            ),
            self.assertRaisesRegex(errors.InstallError, "rolled back"),
        ):
            self._install(payload, current)
        self.assertEqual(payload.events, ["commit", "rollback"])

    def test_legacy_upgrade_rolls_back_after_termination_or_successor_failure(self) -> None:
        failures = (
            (False, errors.InstallError("verified legacy listener did not terminate")),
            (
                True,
                errors.InstallError("successor timeout"),
            ),
        )
        for terminated, failure in failures:
            with self.subTest(failure=failure):
                payload = FakeTransaction()
                adapter = FakeServiceAdapter()
                restored = {"pid": 333, "release": "1.0.26", "accepting": True}
                with (
                    mock.patch.object(
                        apply,
                        "prove_legacy_quiet_window",
                        return_value=self._legacy_listener(),
                    ),
                    mock.patch.object(process, "terminate_pid", return_value=terminated),
                    mock.patch.object(
                        apply,
                        "wait_for_serving_runtime",
                        side_effect=failure if terminated else None,
                    ),
                    mock.patch.object(
                        apply,
                        "wait_for_legacy_runtime",
                        return_value=restored,
                    ) as rollback_runtime,
                    self.assertRaisesRegex(type(failure), str(failure)),
                ):
                    self._install(
                        payload,
                        self._legacy_runtime(),
                        adapter=adapter,
                        allow_legacy_bootstrap=True,
                    )
                self.assertEqual(payload.events, ["commit", "rollback"])
                self.assertEqual(adapter.install_mock.call_count, 2 * int(terminated))
                self.assertEqual(rollback_runtime.call_count, int(terminated))

    def test_legacy_upgrade_rolls_back_when_supervision_replacement_fails(self) -> None:
        payload = FakeTransaction()
        adapter = FakeServiceAdapter()
        adapter.install_mock.side_effect = [RuntimeError("service replacement failed"), None]
        with (
            mock.patch.object(
                apply,
                "prove_legacy_quiet_window",
                return_value=self._legacy_listener(),
            ),
            mock.patch.object(process, "terminate_pid", return_value=True),
            mock.patch.object(apply, "wait_for_legacy_runtime"),
            self.assertRaisesRegex(RuntimeError, "service replacement failed"),
        ):
            self._install(
                payload,
                self._legacy_runtime(),
                adapter=adapter,
                allow_legacy_bootstrap=True,
            )
        self.assertEqual(payload.events, ["commit", "rollback"])
        self.assertEqual(adapter.install_mock.call_count, 2)

    def test_legacy_upgrade_reports_failed_runtime_rollback(self) -> None:
        payload = FakeTransaction()
        adapter = FakeServiceAdapter()
        with (
            mock.patch.object(
                apply,
                "prove_legacy_quiet_window",
                return_value=self._legacy_listener(),
            ),
            mock.patch.object(process, "terminate_pid", return_value=True),
            mock.patch.object(
                apply,
                "wait_for_serving_runtime",
                side_effect=errors.InstallError("successor timeout"),
            ),
            mock.patch.object(
                apply,
                "wait_for_legacy_runtime",
                side_effect=errors.InstallError("rollback timeout"),
            ),
            self.assertRaisesRegex(
                errors.InstallError, "runtime rollback failed: rollback timeout"
            ),
        ):
            self._install(
                payload,
                self._legacy_runtime(),
                adapter=adapter,
                allow_legacy_bootstrap=True,
            )
        self.assertEqual(payload.events, ["commit", "rollback"])

    def test_schema_one_bootstrap_binds_integrity_listener_and_termination_to_old_entrypoint(
        self,
    ) -> None:
        write_retired_projection(self.ctx, version="1.0.26", schema=1)
        legacy_script = str(Path(self.ctx.install_dir, "proxy", "dmx_responses_proxy.py"))
        with (
            mock.patch.object(process, "listener_pids", return_value=[111]),
            mock.patch.object(
                process,
                "process_command",
                return_value=f'{self.ctx.python} "{legacy_script}"',
            ),
        ):
            listener = apply.prove_legacy_quiet_window(
                self.ctx,
                runtime_reader=lambda _ctx: {"active_responses": 0},
                timeout_seconds=0,
                force=True,
            )
        self.assertEqual(
            listener,
            apply.LegacyListener(
                projection.HistoricalProjection(
                    "1.0.26",
                    frozenset(projection._RETIRED_RUNTIME_FILES[1]),
                    legacy_script,
                ),
                process.OwnedProcess(111, legacy_script),
            ),
        )

    def test_force_legacy_bootstrap_never_bypasses_historical_manifest_integrity(self) -> None:
        write_retired_projection(self.ctx, version="1.0.26", schema=1)
        Path(self.ctx.install_dir, "proxy", "dmx_responses_proxy.py").write_bytes(b"tampered")
        with self.assertRaisesRegex(errors.InstallError, "integrity"):
            apply.prove_legacy_quiet_window(
                self.ctx,
                runtime_reader=lambda _ctx: {"active_responses": 0},
                timeout_seconds=0,
                force=True,
            )

    def test_request_handoff_accepts_direct_or_recovered_successor_runtime(self) -> None:
        current = self._protocol_v2_runtime()
        expected = FakeTransaction().expected
        finalized = {"pid": 222, "release": "1.2.3"}
        for request_result, resolution in (
            ({"runtime": finalized}, None),
            ({"runtime": None}, ("finalized", finalized)),
        ):
            with self.subTest(resolution=resolution):
                with (
                    mock.patch.object(apply.handoff, "request", return_value=request_result),
                    mock.patch.object(
                        apply.handoff,
                        "resolve_after_controller_failure",
                        return_value=resolution,
                    ) as resolver,
                ):
                    result = apply.request_handoff(
                        self.ctx,
                        expected,
                        current=current,
                        runtime_reader=lambda _ctx: current,
                        timeout_seconds=0.5,
                    )
                self.assertEqual(result, finalized)
                self.assertEqual(resolver.call_count, int(resolution is not None))

    def test_request_handoff_reraises_the_original_error_after_proven_rollback(self) -> None:
        current = self._protocol_v2_runtime()
        error = errors.InstallError("original handoff failure")
        with (
            mock.patch.object(apply.handoff, "request", side_effect=error),
            mock.patch.object(
                apply.handoff,
                "resolve_after_controller_failure",
                return_value=("rolled_back", current),
            ),
            self.assertRaisesRegex(errors.InstallError, "original handoff failure"),
        ):
            apply.request_handoff(
                self.ctx,
                FakeTransaction().expected,
                current=current,
                runtime_reader=lambda _ctx: current,
                timeout_seconds=1,
            )

    def test_legacy_quiet_window_covers_integrity_listener_force_change_idle_and_timeout(
        self,
    ) -> None:
        def prove(
            runtime_reader: apply.RuntimeReader = lambda _ctx: None,
            *,
            timeout: float = 1,
            force: bool = False,
        ) -> apply.LegacyListener:
            return apply.prove_legacy_quiet_window(
                self.ctx,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout,
                force=force,
            )

        legacy_script = str(Path(self.ctx.install_dir, "proxy", "dmx_responses_proxy.py"))
        verified_manifest = projection.HistoricalProjection(
            "1.0.26", frozenset({"proxy/dmx_responses_proxy.py"}), legacy_script
        )

        with (
            mock.patch.object(
                projection,
                "verify_historical_projection",
                side_effect=errors.InstallError("bad"),
            ),
            self.assertRaisesRegex(errors.InstallError, "integrity"),
        ):
            prove()

        for listeners in ([], [111, 222]):
            with (
                self.subTest(listeners=listeners),
                mock.patch.object(
                    projection, "verify_historical_projection", return_value=verified_manifest
                ),
                mock.patch.object(process, "verified_listener_pids", return_value=listeners),
                self.assertRaisesRegex(errors.InstallError, "exactly one"),
            ):
                prove()

        with (
            mock.patch.object(
                projection, "verify_historical_projection", return_value=verified_manifest
            ),
            mock.patch.object(process, "verified_listener_pids", return_value=[111]),
        ):
            self.assertEqual(
                prove(
                    lambda _ctx: {"active_responses": 9},
                    timeout=0,
                    force=True,
                ),
                apply.LegacyListener(verified_manifest, process.OwnedProcess(111, legacy_script)),
            )

        with (
            mock.patch.object(
                projection, "verify_historical_projection", return_value=verified_manifest
            ),
            mock.patch.object(process, "verified_listener_pids", side_effect=[[111], [222]]),
            mock.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1]),
            self.assertRaisesRegex(errors.InstallError, "changed"),
        ):
            prove(lambda _ctx: {"active_responses": 0})

        readings: list[dict[str, object]] = (
            [{"active_responses": value} for value in (1, 0, True, 0)]
            + [{"release": "1.2.2"}]
            + [{"active_responses": 0}] * 2
        )
        clock = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 6.0, 6.1, 6.2])
        with (
            mock.patch.object(
                projection, "verify_historical_projection", return_value=verified_manifest
            ),
            mock.patch.object(process, "verified_listener_pids", return_value=[111]),
            mock.patch.object(
                apply.time,
                "monotonic",
                side_effect=lambda: next(clock),
            ),
            mock.patch.object(apply.time, "sleep"),
        ):
            self.assertEqual(
                prove(
                    lambda _ctx: readings.pop(0),
                    timeout=10,
                ),
                apply.LegacyListener(verified_manifest, process.OwnedProcess(111, legacy_script)),
            )

        with (
            mock.patch.object(
                projection, "verify_historical_projection", return_value=verified_manifest
            ),
            mock.patch.object(process, "verified_listener_pids", return_value=[111]),
            mock.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2]),
            mock.patch.object(apply.time, "sleep"),
            self.assertRaisesRegex(errors.InstallError, "did not remain idle"),
        ):
            prove(lambda _ctx: {"active_responses": 1}, timeout=0.15)

    def test_wait_for_serving_runtime_rejects_each_identity_and_pid_shape_then_times_out(
        self,
    ) -> None:
        expected = FakeTransaction().expected
        matching: dict[str, object] = {
            "pid": 222,
            "release": expected["release"],
            "serving_payload_sha256": expected["serving_payload_sha256"],
            "payload_manifest_sha256": expected["manifest_sha256"],
            "release_receipt_sha256": expected["release_receipt_sha256"],
            "accepting": True,
            "draining": False,
        }
        snapshots: list[dict[str, object] | None] = [
            None,
            {**matching, "pid": True},
            {**matching, "pid": 0},
            {**matching, "pid": 222},
            {**matching, "pid": 111},
            {**matching, "release": "wrong"},
            {**matching, "serving_payload_sha256": "wrong"},
            {**matching, "payload_manifest_sha256": "wrong"},
            {**matching, "release_receipt_sha256": "wrong"},
            {**matching, "accepting": False},
            {**matching, "draining": True},
            matching,
        ]
        listener_snapshots = [[], [True], [0], [999], [111], *[[222]] * 7]
        with (
            mock.patch.object(
                process, "verified_proxy_listener_pids", side_effect=listener_snapshots
            ),
            mock.patch.object(apply.time, "sleep"),
            mock.patch.object(
                apply.time,
                "monotonic",
                side_effect=map(float, range(13)),
            ),
        ):
            self.assertEqual(
                apply.wait_for_serving_runtime(
                    self.ctx,
                    expected,
                    runtime_reader=lambda _ctx: snapshots.pop(0),
                    timeout_seconds=20,
                    old_pid=111,
                ),
                matching,
            )

        with (
            mock.patch.object(process, "verified_proxy_listener_pids", return_value=[]),
            mock.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2]),
            mock.patch.object(apply.time, "sleep"),
            self.assertRaisesRegex(errors.InstallError, "SERVING identity"),
        ):
            apply.wait_for_serving_runtime(
                self.ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_wait_for_legacy_runtime_requires_exact_accepting_process_identity(self) -> None:
        matching: dict[str, object] = {
            "pid": 222,
            "release": "1.0.26",
            "accepting": True,
        }
        snapshots: list[dict[str, object] | None] = [
            None,
            {**matching, "pid": True},
            {**matching, "pid": 0},
            {**matching, "pid": 999},
            {**matching, "release": "wrong"},
            {**matching, "accepting": False},
            matching,
        ]
        with (
            mock.patch.object(
                process,
                "verified_listener_pids",
                side_effect=[[], [True], [0], [222], [222], [222], [222]],
            ),
            mock.patch.object(apply.time, "monotonic", side_effect=map(float, range(8))),
            mock.patch.object(apply.time, "sleep"),
        ):
            self.assertEqual(
                apply.wait_for_legacy_runtime(
                    self.ctx,
                    release="1.0.26",
                    runtime_reader=lambda _ctx: snapshots.pop(0),
                    timeout_seconds=10,
                ),
                matching,
            )
        with (
            mock.patch.object(process, "verified_listener_pids", return_value=[]),
            mock.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2]),
            mock.patch.object(apply.time, "sleep"),
            self.assertRaisesRegex(errors.InstallError, "historical listener rollback"),
        ):
            apply.wait_for_legacy_runtime(
                self.ctx,
                release="1.0.26",
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_read_runtime_accepts_only_http_200_json_objects(self) -> None:
        class Response:
            def __init__(self, status: int, payload: bytes) -> None:
                self.status = status
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        opener = mock.Mock()
        with mock.patch.object(apply.urllib.request, "build_opener", return_value=opener):
            opener.open.return_value = Response(200, b'{"pid": 222}')
            self.assertEqual(apply.read_runtime(self.ctx), {"pid": 222})
            opener.open.return_value = Response(204, b"")
            self.assertIsNone(apply.read_runtime(self.ctx))
            opener.open.return_value = Response(200, b"[]")
            self.assertIsNone(apply.read_runtime(self.ctx))
            opener.open.return_value = Response(200, b"not-json")
            self.assertIsNone(apply.read_runtime(self.ctx))
            opener.open.side_effect = urllib.error.URLError("offline")
            self.assertIsNone(apply.read_runtime(self.ctx))


class TestInstallComposition(unittest.TestCase):
    """Keep admission, transaction, and apply on one source-side entry."""

    @staticmethod
    def _arguments() -> InstallArguments:
        return InstallArguments(
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
            adapter=FakeServiceAdapter(),
        )

    def test_install_release_verifies_live_publication_before_source_admission(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        authority = mock.create_autospec(publication.PublishedRelease, instance=True)
        released = mock.Mock()
        tx = mock.Mock()
        with (
            mock.patch.object(install.release_admission, "require_clean_checkout"),
            mock.patch.object(install.publication, "verify", return_value=authority) as verify,
            mock.patch.object(install, "admit_released_payload", return_value=released) as admit,
            mock.patch.object(install.transaction, "begin_transaction", return_value=tx) as begin,
            mock.patch.object(
                install.apply, "install", return_value={"mode": "fresh-install"}
            ) as deploy,
        ):
            result = install.install_release(ctx, **self._arguments())
        verify.assert_called_once()
        admit.assert_called_once_with(authority, trust_anchor=Path("/external/allowed-signers"))
        begin.assert_called_once_with(ctx, released)
        deploy.assert_called_once()
        self.assertEqual(result["mode"], "fresh-install")

    def test_install_release_rechecks_checkout_after_live_publication(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        authority = mock.create_autospec(publication.PublishedRelease, instance=True)
        arguments = self._arguments()
        with (
            mock.patch.object(install.release_admission, "require_clean_checkout") as clean,
            mock.patch.object(install.publication, "verify", return_value=authority),
            mock.patch.object(
                install,
                "admit_released_payload",
                side_effect=install.release_admission.ReleaseSourceError("clean checkout required"),
            ),
            mock.patch.object(install.transaction, "begin_transaction") as begin,
            self.assertRaisesRegex(install.release_admission.ReleaseSourceError, "clean checkout"),
        ):
            install.install_release(ctx, **arguments)
        clean.assert_called_once()
        begin.assert_not_called()

    def test_publication_verification_failure_refuses_before_source_admission(self) -> None:
        with (
            mock.patch.object(install.release_admission, "require_clean_checkout"),
            mock.patch.object(
                install.publication,
                "verify",
                side_effect=publication.PublicationError("GitHub release is unavailable"),
            ),
            mock.patch.object(install.release_admission, "admit") as admit,
            self.assertRaisesRegex(publication.PublicationError, "GitHub release"),
        ):
            install.install_release(install_context(Path(tempfile.mkdtemp())), **self._arguments())
        admit.assert_not_called()

    def test_install_has_no_json_publication_proof_loader(self) -> None:
        self.assertFalse(hasattr(install, "publication_proof_from_file"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
