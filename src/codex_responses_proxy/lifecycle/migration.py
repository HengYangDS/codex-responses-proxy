"""Removal of exact privacy and executable residue from retired payloads."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from codex_responses_proxy import errors
from codex_responses_proxy.service import digest
from codex_responses_proxy.lifecycle import owned_files, rollback
from codex_responses_proxy.lifecycle import context as runtime_context

_LEGACY_CAPTURE_NAME = re.compile(r"^reject-[^/]+\.json$")


def remove_legacy_captures(ctx: runtime_context.RuntimeContext) -> None:
    """Remove exact retired raw captures without reading their contents."""

    log_root = Path(ctx.log_dir)
    if log_root.is_dir() and not log_root.is_symlink():
        try:
            entries = tuple(log_root.iterdir())
        except OSError as exc:
            raise errors.InstallError("retired runtime residue inventory failed") from exc
        for entry in entries:
            if _LEGACY_CAPTURE_NAME.fullmatch(entry.name) is None:
                continue
            try:
                if entry.is_symlink() or not entry.is_file():
                    continue
                entry.unlink()
            except OSError as exc:
                raise errors.InstallError("legacy raw request capture cleanup failed") from exc


def remove_retired_paths(
    ctx: runtime_context.RuntimeContext,
    snapshot: rollback.RollbackInventory,
) -> None:
    """Unlink only retired files admitted into the rollback snapshot."""

    install = Path(ctx.install_dir)
    for relative in sorted(
        snapshot.retired,
        key=lambda value: len(PurePosixPath(value).parts),
        reverse=True,
    ):
        path = owned_files.regular_file(install, relative, "retired installed payload")
        if digest.sha256_file(path) != snapshot.present[relative][0]:
            raise errors.InstallError(
                f"retired installed payload changed after snapshot: {relative}"
            )
        try:
            path.unlink()
        except OSError as exc:
            raise errors.InstallError(f"retired installed path cleanup failed: {relative}") from exc
    _remove_empty_retired_directories(install)


def _remove_empty_retired_directories(install: Path) -> None:
    for relative in owned_files.RETIRED_INSTALL_DIRECTORIES:
        root = install / relative
        if root.is_symlink() or not root.exists():
            continue
        if not root.is_dir():
            raise errors.InstallError(f"retired installed path is not a directory: {relative}")
        try:
            directories = sorted(
                (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
        except OSError as exc:
            raise errors.InstallError(f"retired installed path cleanup failed: {relative}") from exc
        for directory in (*directories, root):
            try:
                directory.rmdir()
            except OSError as exc:
                try:
                    nonempty = any(directory.iterdir())
                except OSError:
                    nonempty = False
                if nonempty:
                    continue
                raise errors.InstallError(
                    f"retired installed path cleanup failed: "
                    f"{directory.relative_to(install).as_posix()}"
                ) from exc
