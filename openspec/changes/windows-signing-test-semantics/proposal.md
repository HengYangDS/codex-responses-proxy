# Align signing tests with platform ownership

## Why

The release-signing contract permits terminal-newline repair only on POSIX.
One integration test still required that repair on every platform, contradicting
the Windows fail-closed contract and causing the Windows CI matrix to fail.

## What changes

- Scope the missing-newline success case to POSIX.
- Keep the Windows fail-closed regression as the Windows contract proof.

## Boundaries

Production signing behavior, release identity, trust, Forge workflows, and
runtime code remain unchanged.
