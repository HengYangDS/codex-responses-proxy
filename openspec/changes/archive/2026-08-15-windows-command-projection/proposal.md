# Windows-Native Command Projection

## Why

The product deliberately uses a symbolic link on POSIX and a hard link on
Windows. Several lifecycle tests nevertheless assert POSIX-only link behavior,
and one CLI fixture records POSIX paths while running on Windows. The Windows
matrix therefore rejects the product's intended native projection contract.

## What Changes

- Define command ownership by native link identity rather than by one link kind.
- Prove Windows hard-link installation, status, rollback, and failure handling.
- Keep exact symbolic-link assertions on POSIX.
- Make lifecycle fixtures use paths native to the host that evaluates them.

## Non-goals

- Replacing the native projection with copied executables, wrappers, or a
  compatibility layer.
- Weakening foreign-path detection, rollback identity, or POSIX semantics.
- Changing client configuration, provider routing, or Codex session state.
