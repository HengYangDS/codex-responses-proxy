"""Immutable payload generations selected from one stable control root."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory

if TYPE_CHECKING:
    from codex_responses_proxy.lifecycle import context as runtime_context

SELECTOR_FILENAME = identity.PAYLOAD_SELECTOR_FILENAME
SELECTOR_SCHEMA = identity.PAYLOAD_SELECTOR_SCHEMA
GENERATIONS_DIRNAME = identity.PAYLOAD_GENERATIONS_DIRNAME
Selection = identity.PayloadSelection


def root(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the immutable payload-generation store."""
    return Path(ctx.install_dir, GENERATIONS_DIRNAME)


def path(ctx: runtime_context.RuntimeContext, generation: str) -> Path:
    """Return one validated payload-generation directory."""
    _require_name(generation)
    return root(ctx) / generation


def selector_path(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the durable active-generation selector."""
    return Path(ctx.install_dir, SELECTOR_FILENAME)


def context(ctx: runtime_context.RuntimeContext, generation: str) -> runtime_context.RuntimeContext:
    """Project one immutable generation through the stable runtime settings."""
    generation_root = path(ctx, generation)
    executable_name = Path(ctx.executable).name.lower()
    windows = executable_name.endswith(".exe")
    if not windows:
        stable_executable = Path(ctx.install_dir, inventory.EXECUTABLE)
        stable_windows_executable = Path(ctx.install_dir, inventory.WINDOWS_EXECUTABLE)
        if Path(ctx.executable) == stable_windows_executable or (
            Path(ctx.executable) != stable_executable
            and stable_windows_executable.exists()
            and not stable_executable.exists()
        ):
            windows = True
    return replace(
        ctx,
        executable=inventory.installed_executable(str(generation_root), windows=windows),
    )


def read(ctx: runtime_context.RuntimeContext) -> Selection | None:
    """Read and validate the selected generation without following links."""
    selector = selector_path(ctx)
    if not selector.exists() and not selector.is_symlink():
        return None
    if selector.is_symlink() or not selector.is_file():
        raise errors.InstallError("payload generation selector is invalid")
    try:
        selection = identity.read_payload_selection(selector)
    except ValueError:
        raise errors.InstallError("payload generation selector is invalid") from None

    for generation in (selection.active, selection.predecessor):
        if generation is None:
            continue
        selected = path(ctx, generation)
        if selected.is_symlink() or not selected.is_dir():
            raise errors.InstallError("selected payload generation is unavailable or invalid")
    return selection


def selected_context(
    ctx: runtime_context.RuntimeContext,
) -> runtime_context.RuntimeContext:
    """Return the active generation context, or the legacy bootstrap context."""
    selection = read(ctx)
    return context(ctx, selection.active) if selection is not None else ctx


def owned_contexts(
    ctx: runtime_context.RuntimeContext,
) -> tuple[runtime_context.RuntimeContext, ...]:
    """Return every exact immutable generation owned by the stable control root."""
    generations = root(ctx)
    if not generations.exists() and not generations.is_symlink():
        return ()
    if generations.is_symlink() or not generations.is_dir():
        raise errors.InstallError("payload generation store is unavailable or invalid")
    try:
        entries = tuple(sorted(generations.iterdir(), key=lambda entry: entry.name))
    except OSError as exc:
        raise errors.InstallError("payload generation store is unreadable") from exc
    contexts = []
    for entry in entries:
        _require_name(entry.name)
        if entry.is_symlink() or not entry.is_dir():
            raise errors.InstallError("payload generation store is invalid")
        contexts.append(context(ctx, entry.name))
    return tuple(contexts)


def select(
    ctx: runtime_context.RuntimeContext,
    *,
    active: str,
    predecessor: str | None,
) -> None:
    """Atomically select one verified generation and at most one predecessor."""
    _require_generation(ctx, active, "active")
    if predecessor is not None:
        _require_generation(ctx, predecessor, "predecessor")
        if predecessor == active:
            raise errors.InstallError("payload generation selector is invalid")
    owned_files.write_bytes(
        selector_path(ctx),
        digest.canonical_json(
            {
                "schema_version": SELECTOR_SCHEMA,
                "active": active,
                "predecessor": predecessor,
            }
        ),
        mode=0o600,
        root=Path(ctx.install_dir),
    )


def materialize_legacy_projection(
    ctx: runtime_context.RuntimeContext,
    source: Path,
    generation: str,
    present: Mapping[str, tuple[str, int]],
) -> runtime_context.RuntimeContext:
    """Copy one verified legacy snapshot into an immutable generation."""
    target = path(ctx, generation)
    projected = context(ctx, generation)
    if target.is_dir() and not target.is_symlink():
        _require_snapshot_projection(target, present)
        return projected
    if target.exists() or target.is_symlink() or source.is_symlink() or not source.is_dir():
        raise errors.InstallError("predecessor payload generation source is invalid")
    staging = target.with_name(f".{target.name}.staging")
    if staging.exists() or staging.is_symlink():
        if staging.is_symlink() or not staging.is_dir():
            raise errors.InstallError("predecessor payload generation staging is invalid")
        shutil.rmtree(staging)
    staging.mkdir(parents=True, mode=0o700)
    try:
        for relative, (expected_sha256, expected_mode) in sorted(present.items()):
            source_file = owned_files.regular_file(source, relative, "predecessor snapshot")
            if (
                digest.sha256_file(source_file) != expected_sha256
                or source_file.stat(follow_symlinks=False).st_mode & 0o777 != expected_mode
            ):
                raise errors.InstallError(f"predecessor payload snapshot changed: {relative}")
            target_file = owned_files.path(staging, relative)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target_file, follow_symlinks=False)
            os.chmod(target_file, expected_mode)
        staging_executable = inventory.installed_executable(
            str(staging),
            windows=inventory.WINDOWS_EXECUTABLE in present,
        )
        runtime_spec.write(
            replace(
                projected,
                install_dir=str(target),
                executable=staging_executable,
            )
        )
        _require_snapshot_projection(staging, present, runtime_root=target)
        os.replace(staging, target)
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise errors.InstallError("legacy payload migration failed") from exc
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _require_snapshot_projection(target, present)
    return projected


def retire_legacy_projection(
    source: Path,
    present: Mapping[str, tuple[str, int]],
) -> None:
    """Remove the verified flat payload after its generation is durable."""
    for relative in sorted(
        present,
        key=lambda value: len(Path(value).parts),
        reverse=True,
    ):
        target = owned_files.path(source, relative)
        if not target.exists() and not target.is_symlink():
            continue
        expected_sha256, expected_mode = present[relative]
        target = owned_files.regular_file(source, relative, "legacy payload retirement")
        if (
            digest.sha256_file(target) != expected_sha256
            or target.stat(follow_symlinks=False).st_mode & 0o777 != expected_mode
        ):
            raise errors.InstallError(f"legacy payload changed before retirement: {relative}")
        try:
            target.unlink()
        except OSError as exc:
            raise errors.InstallError(f"legacy payload retirement failed: {relative}") from exc
    projection.remove_empty_owned_directories(source, set(present))


def _require_snapshot_projection(
    target: Path,
    present: Mapping[str, tuple[str, int]],
    *,
    runtime_root: Path | None = None,
) -> None:
    """Require one generation to be the exact declared legacy snapshot."""
    runtime_root = target if runtime_root is None else runtime_root
    expected_files = set(present) | {inventory.RUNTIME_CONFIG_FILENAME}
    actual = {
        item.relative_to(target).as_posix()
        for item in target.rglob("*")
        if item.is_file() or item.is_symlink()
    }
    if actual != expected_files:
        raise errors.InstallError("predecessor payload generation inventory is invalid")
    for relative, (expected_sha256, expected_mode) in present.items():
        item = owned_files.regular_file(target, relative, "predecessor payload generation")
        if relative == inventory.RUNTIME_CONFIG_FILENAME:
            configured_root = owned_files.read_canonical_json(
                item,
                "predecessor runtime configuration",
            ).get("install_dir")
            if configured_root != str(runtime_root) or (
                item.stat(follow_symlinks=False).st_mode & 0o777 != expected_mode
            ):
                raise errors.InstallError("predecessor runtime configuration is invalid")
            continue
        if (
            digest.sha256_file(item) != expected_sha256
            or item.stat(follow_symlinks=False).st_mode & 0o777 != expected_mode
        ):
            raise errors.InstallError(f"predecessor payload generation changed: {relative}")
    if target == runtime_root:
        environment = runtime_spec.environment(target / inventory.RUNTIME_CONFIG_FILENAME)
        if environment[runtime_config.HOME_ENV] != str(runtime_root):
            raise errors.InstallError("predecessor runtime configuration is invalid")
    executable = inventory.installed_executable(
        str(target), windows=inventory.WINDOWS_EXECUTABLE in present
    )
    if identity.committed_payload(Path(executable)) is None:
        raise errors.InstallError("predecessor payload generation is invalid")


def clear(ctx: runtime_context.RuntimeContext) -> None:
    """Remove only the owned selector."""
    selector = selector_path(ctx)
    if selector.is_symlink():
        raise errors.InstallError("payload generation selector is a symbolic link")
    try:
        selector.unlink(missing_ok=True)
    except OSError as exc:
        raise errors.InstallError("payload generation selector removal failed") from exc


def remove(ctx: runtime_context.RuntimeContext, generation: str) -> None:
    """Remove one exact unselected generation."""
    selection = read(ctx)
    if selection is not None and generation in {
        selection.active,
        selection.predecessor,
    }:
        raise errors.InstallError("selected payload generation cannot be removed")
    target = path(ctx, generation)
    if target.is_symlink():
        raise errors.InstallError("payload generation is a symbolic link")
    if target.exists():
        if not target.is_dir():
            raise errors.InstallError("payload generation is invalid")
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise errors.InstallError("payload generation removal failed") from exc
    generations = root(ctx)
    try:
        if generations.is_dir() and not any(generations.iterdir()):
            generations.rmdir()
    except OSError as exc:
        raise errors.InstallError("empty payload generation store removal failed") from exc


def prune(ctx: runtime_context.RuntimeContext, selection: Selection) -> None:
    """Retain exactly the selected active and predecessor generations."""
    generations = root(ctx)
    if generations.is_symlink() or not generations.is_dir():
        raise errors.InstallError("payload generation store is unavailable or invalid")
    keep = {selection.active, selection.predecessor} - {None}
    try:
        for entry in generations.iterdir():
            if entry.name in keep:
                if entry.is_symlink() or not entry.is_dir():
                    raise errors.InstallError("payload generation store is invalid")
                continue
            if entry.is_symlink() or not entry.is_dir():
                raise errors.InstallError("payload generation store is invalid")
            shutil.rmtree(entry)
    except errors.InstallError:
        raise
    except OSError as exc:
        raise errors.InstallError("payload generation cleanup failed") from exc


def _require_generation(ctx: runtime_context.RuntimeContext, generation: str, role: str) -> None:
    selected = path(ctx, generation)
    if selected.is_symlink() or not selected.is_dir():
        raise errors.InstallError(f"{role} payload generation is unavailable or invalid")
    projected = context(ctx, generation)
    if identity.committed_payload(Path(projected.executable)) is None:
        raise errors.InstallError(f"{role} payload generation identity is invalid")


def _require_name(generation: str) -> None:
    try:
        identity.require_payload_generation_name(generation)
    except ValueError:
        raise errors.InstallError("payload generation identity is invalid") from None
