"""Rollback authority derived from the immutable payload selector."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import rollback
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.lifecycle import transaction as payload_transaction
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import begin_transaction
from tests.lifecycle.fixtures import executable_relative
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.fixtures import install_payload
from tests.lifecycle.fixtures import released_artifact


def install_successor(ctx, *, mocker):
    """Install two immutable generations and retain the first as predecessor."""
    first = install_payload(ctx, "1.2.2", mocker=mocker)
    second = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
    second.commit_projection()
    second.activate()
    second.finalize({"pid": 2})
    ctx.executable = second.context.executable
    return first, second


def test_selector_is_the_only_retained_rollback_authority(tmp_path: Path, *, mocker) -> None:
    ctx = install_context(tmp_path)
    first, second = install_successor(ctx, mocker=mocker)

    selection = generation.read(ctx)
    retained = rollback.load_retained(ctx)

    assert selection == generation.Selection(
        active=str(second.expected["transaction_id"]),
        predecessor=str(first.expected["transaction_id"]),
    )
    assert selection.predecessor is not None
    assert retained.root == generation.path(ctx, selection.predecessor)
    assert retained.predecessor.release == "1.2.2"
    assert retained.successor.release == "1.2.3"


def test_removing_retained_predecessor_preserves_only_active_generation(
    tmp_path: Path, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    first, second = install_successor(ctx, mocker=mocker)

    rollback.remove_retained(ctx)

    assert generation.read(ctx) == generation.Selection(
        active=str(second.expected["transaction_id"]),
        predecessor=None,
    )
    assert generation.path(ctx, str(second.expected["transaction_id"])).is_dir()
    assert not generation.path(ctx, str(first.expected["transaction_id"])).exists()
    assert rollback.load_retained_or_none(ctx) is None


def test_clean_absence_has_no_retained_rollback(tmp_path: Path, *, mocker) -> None:
    """A fresh selected generation exposes no rollback operation or residue."""
    ctx = install_context(tmp_path)
    install_payload(ctx, mocker=mocker)

    rollback.remove_retained(ctx)

    with pytest.raises(errors.InstallError, match="predecessor is unavailable"):
        rollback.load_retained(ctx)


def test_retained_predecessor_corruption_is_rejected_from_selected_generation(
    tmp_path: Path, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    first, _second = install_successor(ctx, mocker=mocker)
    predecessor = generation.context(ctx, str(first.expected["transaction_id"]))
    Path(predecessor.executable).write_bytes(b"corrupt")

    with pytest.raises(
        errors.InstallError,
        match="predecessor generation identity is invalid",
    ):
        rollback.load_retained(ctx)


def test_retained_successor_corruption_is_rejected_from_selected_generation(
    tmp_path: Path, *, mocker
) -> None:
    """The active generation identity remains part of rollback admission."""
    ctx = install_context(tmp_path)
    _first, second = install_successor(ctx, mocker=mocker)
    successor = generation.context(ctx, str(second.expected["transaction_id"]))
    Path(successor.executable).write_bytes(b"corrupt")

    with pytest.raises(errors.InstallError, match="successor generation identity is invalid"):
        rollback.load_retained(ctx)


def test_retained_installed_binding_drift_is_rejected(tmp_path: Path, *, mocker) -> None:
    """Rollback admission binds the selector to the exact installed successor record."""
    ctx = install_context(tmp_path)
    _first, _second = install_successor(ctx, mocker=mocker)
    installed = rollback.state.read_installed(ctx)
    assert installed is not None
    installed["version"] = "1.2.4"
    rollback.owned_files.write_bytes(
        rollback.state.installed_path(ctx),
        digest.canonical_json(installed),
        mode=0o600,
    )

    with pytest.raises(errors.InstallError, match="installed binding is invalid"):
        rollback.load_retained(ctx)


@pytest.mark.parametrize("residue_kind", ["directory", "file", "symlink"])
def test_unselected_generation_residue_invalidates_retained_authority(
    tmp_path: Path, residue_kind: str, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    _first, _second = install_successor(ctx, mocker=mocker)
    residue = generation.root(ctx) / ("f" * 32)
    if residue_kind == "directory":
        residue.mkdir()
    elif residue_kind == "file":
        residue.write_text("unselected\n", encoding="utf-8")
    else:
        target = tmp_path / "external-generation"
        target.mkdir()
        residue.symlink_to(target, target_is_directory=True)

    with pytest.raises(errors.InstallError, match="not closed over its selector"):
        rollback.load_retained(ctx)


def test_orphan_generation_store_is_not_reported_as_clean_absence(
    tmp_path: Path, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    transaction = begin_transaction(ctx, released_artifact("1.2.2"), mocker=mocker)
    transaction.commit_projection()
    generation.clear(ctx)

    with pytest.raises(errors.InstallError, match="without a durable selector"):
        rollback.load_retained_or_none(ctx)


def test_rollback_transaction_reuses_the_selected_predecessor_generation(
    tmp_path: Path, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    _first, _second = install_successor(ctx, mocker=mocker)

    retained = rollback.load_retained(ctx)
    before = generation.read(ctx)
    assert before is not None
    assert before.predecessor is not None
    generations_before = {path.name for path in generation.root(ctx).iterdir()}

    transaction = payload_transaction.begin_rollback_transaction(ctx, retained)
    transaction.commit_projection()

    assert Path(transaction.context.payload_dir) == retained.root
    assert generation.read(ctx) == before
    assert {path.name for path in generation.root(ctx).iterdir()} == generations_before

    transaction.activate()
    transaction.finalize({"pid": 3})

    assert generation.read(ctx) == generation.Selection(
        active=before.predecessor,
        predecessor=before.active,
    )
    assert {path.name for path in generation.root(ctx).iterdir()} == generations_before


def test_control_context_remains_on_the_newest_selected_release(tmp_path: Path, *, mocker) -> None:
    """Serving rollback never downgrades the installed lifecycle command plane."""
    ctx = install_context(tmp_path)
    first, second = install_successor(ctx, mocker=mocker)

    assert generation.control_context(ctx).executable == second.context.executable

    generation.select(
        ctx,
        active=str(first.expected["transaction_id"]),
        predecessor=str(second.expected["transaction_id"]),
    )

    assert generation.control_context(ctx).executable == second.context.executable


def test_selector_rejects_invalid_carriers_and_values(tmp_path: Path) -> None:
    """Selector parsing fails closed for every authority-shape violation."""
    active = "a" * 32
    cases = (
        ("schema", {"schema_version": 2, "active": active, "predecessor": None}),
        ("active-type", {"schema_version": 1, "active": 1, "predecessor": None}),
        ("active-name", {"schema_version": 1, "active": "bad", "predecessor": None}),
        ("predecessor-type", {"schema_version": 1, "active": active, "predecessor": 1}),
        (
            "same-generation",
            {"schema_version": 1, "active": active, "predecessor": active},
        ),
        (
            "extra-field",
            {
                "schema_version": 1,
                "active": active,
                "predecessor": None,
                "parallel_authority": True,
            },
        ),
        (
            "missing-generation",
            {"schema_version": 1, "active": active, "predecessor": None},
        ),
    )
    for name, value in cases:
        ctx = install_context(tmp_path / name)
        selector = generation.selector_path(ctx)
        selector.parent.mkdir(parents=True)
        selector.write_bytes(digest.canonical_json(value))
        with pytest.raises(errors.InstallError, match=r"selector|identity|unavailable"):
            generation.read(ctx)

    ctx = install_context(tmp_path / "directory")
    generation.selector_path(ctx).mkdir(parents=True)
    with pytest.raises(errors.InstallError, match="selector is invalid"):
        generation.read(ctx)

    ctx = install_context(tmp_path / "symlink")
    target = tmp_path / "selector-target"
    target.write_text("{}", encoding="utf-8")
    selector = generation.selector_path(ctx)
    selector.parent.mkdir(parents=True)
    selector.symlink_to(target)
    with pytest.raises(errors.InstallError, match="selector is invalid"):
        generation.read(ctx)


def test_generation_selection_requires_valid_distinct_payloads(tmp_path: Path, *, mocker) -> None:
    """Selection accepts only complete identities and distinct predecessor authority."""
    ctx = install_context(tmp_path)
    installed = install_payload(ctx, mocker=mocker)
    active = str(installed.expected["transaction_id"])

    with pytest.raises(errors.InstallError, match="selector is invalid"):
        generation.select(ctx, active=active, predecessor=active)
    with pytest.raises(errors.InstallError, match="predecessor payload generation"):
        generation.select(ctx, active=active, predecessor="b" * 32)

    invalid = "c" * 32
    generation.path(ctx, invalid).mkdir()
    with pytest.raises(errors.InstallError, match="active payload generation identity"):
        generation.select(ctx, active=invalid, predecessor=None)


def test_generation_removal_and_pruning_fail_closed(tmp_path: Path, *, mocker) -> None:
    """Cleanup preserves selected payloads and rejects ambiguous filesystem objects."""
    ctx = install_context(tmp_path)
    installed = install_payload(ctx, mocker=mocker)
    active = str(installed.expected["transaction_id"])
    selection = generation.Selection(active, None)

    with pytest.raises(errors.InstallError, match="cannot be removed"):
        generation.remove(ctx, active)
    generation.remove(ctx, "d" * 32)

    invalid = generation.path(ctx, "e" * 32)
    invalid.write_text("not a generation\n", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="generation is invalid"):
        generation.remove(ctx, invalid.name)
    invalid.unlink()

    outside = tmp_path / "outside-generation"
    outside.mkdir()
    invalid.symlink_to(outside, target_is_directory=True)
    with pytest.raises(errors.InstallError, match="symbolic link"):
        generation.remove(ctx, invalid.name)
    invalid.unlink()

    residue = generation.path(ctx, "f" * 32)
    residue.mkdir()
    remove = mocker.patch.object(generation.shutil, "rmtree", side_effect=OSError("blocked"))
    with pytest.raises(errors.InstallError, match="cleanup failed"):
        generation.prune(ctx, selection)
    mocker.stop(remove)

    store = generation.root(ctx)
    store.rename(tmp_path / "generation-store")
    store.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="store is unavailable"):
        generation.prune(ctx, selection)


def test_generation_cleanup_reports_exact_filesystem_failures(tmp_path: Path, *, mocker) -> None:
    """Owned selector and generation cleanup never hide filesystem failures."""
    ctx = install_context(tmp_path)
    selector = generation.selector_path(ctx)
    selector.parent.mkdir(parents=True)

    outside = tmp_path / "outside-selector"
    outside.write_text("foreign\n", encoding="utf-8")
    selector.symlink_to(outside)
    with pytest.raises(errors.InstallError, match="selector is a symbolic link"):
        generation.clear(ctx)
    selector.unlink()

    selector.write_text("retained\n", encoding="utf-8")
    unlink = mocker.patch.object(Path, "unlink", autospec=True, side_effect=OSError("blocked"))
    with pytest.raises(errors.InstallError, match="selector removal failed"):
        generation.clear(ctx)
    mocker.stop(unlink)
    selector.unlink()

    target = generation.path(ctx, "e" * 32)
    target.mkdir(parents=True)
    remove = mocker.patch.object(generation.shutil, "rmtree", side_effect=OSError("blocked"))
    with pytest.raises(errors.InstallError, match="generation removal failed"):
        generation.remove(ctx, target.name)
    mocker.stop(remove)

    empty_ctx = install_context(tmp_path / "empty-store")
    empty_target = generation.path(empty_ctx, "f" * 32)
    empty_target.mkdir(parents=True)
    remove_store = mocker.patch.object(Path, "rmdir", autospec=True, side_effect=OSError("busy"))
    with pytest.raises(errors.InstallError, match="empty payload generation store removal failed"):
        generation.remove(empty_ctx, empty_target.name)
    remove_store.assert_called_once_with(generation.root(empty_ctx))


def test_owned_generation_inventory_distinguishes_absence_from_corruption(
    tmp_path: Path,
) -> None:
    """Lifecycle cleanup enumerates only valid generation directories."""
    ctx = install_context(tmp_path)
    assert generation.owned_contexts(ctx) == ()

    store = generation.root(ctx)
    store.parent.mkdir(parents=True)
    store.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="store is unavailable"):
        generation.owned_contexts(ctx)
    store.unlink()

    store.mkdir()
    (store / "not-a-generation").mkdir()
    with pytest.raises(errors.InstallError, match="generation identity is invalid"):
        generation.owned_contexts(ctx)
    (store / "not-a-generation").rmdir()

    valid = store / ("a" * 32)
    valid.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="generation store is invalid"):
        generation.owned_contexts(ctx)
    valid.unlink()

    outside = tmp_path / "outside-generation"
    outside.mkdir()
    valid.symlink_to(outside, target_is_directory=True)
    with pytest.raises(errors.InstallError, match="generation store is invalid"):
        generation.owned_contexts(ctx)


def test_legacy_generation_rejects_snapshot_and_live_drift(tmp_path: Path, *, mocker) -> None:
    """Migration uses one exact durable inventory for materialization and retirement."""
    ctx = install_context(tmp_path)
    legacy = install_payload(ctx, "1.2.2", mocker=mocker)
    legacy_root = Path(legacy.context.payload_dir)
    flat = Path(ctx.install_dir)
    for child in tuple(legacy_root.iterdir()):
        child.rename(flat / child.name)
    generation.clear(ctx)
    legacy_root.rmdir()
    ctx.executable = str(flat / executable_relative())

    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    snapshot = rollback.write_legacy_snapshot(ctx, snapshot_root)
    executable = snapshot_root / executable_relative()
    executable.write_bytes(b"changed")
    with pytest.raises(errors.InstallError, match="snapshot changed"):
        generation.materialize_legacy_projection(
            ctx,
            snapshot_root,
            str(legacy.expected["transaction_id"]),
            snapshot.present,
        )

    executable.write_bytes((flat / executable_relative()).read_bytes())
    executable.chmod(snapshot.present[executable_relative()][1])
    generation.materialize_legacy_projection(
        ctx,
        snapshot_root,
        str(legacy.expected["transaction_id"]),
        snapshot.present,
    )
    (flat / inventory.PROVIDER_MANIFEST).write_text("changed\n", encoding="utf-8")
    with pytest.raises(errors.InstallError, match="changed before retirement"):
        generation.retire_legacy_projection(flat, snapshot.present)


def test_legacy_generation_rejects_invalid_staging(tmp_path: Path, *, mocker) -> None:
    """A foreign staging carrier cannot be adopted or overwritten."""
    ctx = install_context(tmp_path)
    legacy = install_payload(ctx, "1.2.2", mocker=mocker)
    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    snapshot = rollback.write_legacy_snapshot(legacy.context, snapshot_root)
    generation_id = "d" * 32
    staging = generation.path(ctx, generation_id).with_name(f".{generation_id}.staging")
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text("foreign\n", encoding="utf-8")

    with pytest.raises(errors.InstallError, match="staging is invalid"):
        generation.materialize_legacy_projection(
            ctx,
            snapshot_root,
            generation_id,
            snapshot.present,
        )


def test_legacy_generation_reuses_only_the_exact_materialized_snapshot(
    tmp_path: Path, *, mocker
) -> None:
    """An existing predecessor generation must equal the durable migration snapshot."""
    ctx = install_context(tmp_path)
    legacy = install_payload(ctx, "1.2.2", mocker=mocker)
    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    snapshot = rollback.write_legacy_snapshot(legacy.context, snapshot_root)
    generation_id = "d" * 32
    target = generation.path(ctx, generation_id)
    staging = target.with_name(f".{generation_id}.staging")
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    (staging / "interrupted").write_text("stale\n", encoding="utf-8")

    generation.materialize_legacy_projection(
        ctx,
        snapshot_root,
        generation_id,
        snapshot.present,
    )
    assert not staging.exists()
    assert generation.materialize_legacy_projection(
        ctx,
        snapshot_root,
        generation_id,
        snapshot.present,
    ).payload_dir == str(target)

    (target / executable_relative()).write_bytes(b"changed")
    with pytest.raises(errors.InstallError, match="generation changed"):
        generation.materialize_legacy_projection(
            ctx,
            snapshot_root,
            generation_id,
            snapshot.present,
        )


def test_legacy_retirement_is_idempotent_after_owned_file_deletion(
    tmp_path: Path, *, mocker
) -> None:
    """Interrupted retirement can resume without recreating an already deleted file."""
    ctx = install_context(tmp_path)
    legacy = install_payload(ctx, "1.2.2", mocker=mocker)
    legacy_root = Path(legacy.context.payload_dir)
    flat = Path(ctx.install_dir)
    for child in tuple(legacy_root.iterdir()):
        child.rename(flat / child.name)
    generation.clear(ctx)
    legacy_root.rmdir()
    ctx.executable = str(flat / executable_relative())

    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    snapshot = rollback.write_legacy_snapshot(ctx, snapshot_root)
    generation.materialize_legacy_projection(
        ctx,
        snapshot_root,
        str(legacy.expected["transaction_id"]),
        snapshot.present,
    )
    already_retired = flat / executable_relative()
    already_retired.unlink()

    generation.retire_legacy_projection(flat, snapshot.present)

    assert not already_retired.exists()
    for relative in snapshot.present:
        assert not (flat / relative).exists()


def test_legacy_generation_projects_an_executable_local_runtime_root(
    tmp_path: Path, *, mocker
) -> None:
    """A published predecessor must accept its carrier after immutable migration."""
    ctx = install_context(tmp_path)
    legacy = install_payload(ctx, "1.2.2", mocker=mocker)
    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    snapshot = rollback.write_legacy_snapshot(legacy.context, snapshot_root)

    projected = generation.materialize_legacy_projection(
        ctx,
        snapshot_root,
        "e" * 32,
        snapshot.present,
    )

    environment = runtime_spec.environment(runtime_spec.path(projected))
    assert environment[runtime_config.HOME_ENV] == projected.payload_dir


@pytest.mark.parametrize("carrier", ["target-file", "source-file", "source-symlink"])
def test_legacy_generation_rejects_invalid_source_carriers(
    tmp_path: Path, carrier: str, *, mocker
) -> None:
    """Migration rejects non-directory sources and pre-existing target carriers."""
    ctx = install_context(tmp_path)
    legacy = install_payload(ctx, "1.2.2", mocker=mocker)
    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    snapshot = rollback.write_legacy_snapshot(legacy.context, snapshot_root)
    generation_id = "d" * 32
    target = generation.path(ctx, generation_id)
    source = snapshot_root
    if carrier == "target-file":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("foreign\n", encoding="utf-8")
    elif carrier == "source-file":
        source = tmp_path / "snapshot-file"
        source.write_text("foreign\n", encoding="utf-8")
    else:
        source = tmp_path / "snapshot-link"
        source.symlink_to(snapshot_root, target_is_directory=True)

    with pytest.raises(errors.InstallError, match="source is invalid"):
        generation.materialize_legacy_projection(
            ctx,
            source,
            generation_id,
            snapshot.present,
        )
