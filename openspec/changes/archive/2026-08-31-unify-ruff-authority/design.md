## Context

The general Ruff policy already selects the complete admitted rule set, while a
second file selects only `D` rules and repeats the same target version. Both are
invoked by the same Nox sessions.

## Goals / Non-Goals

**Goals:**

- Retain one native Ruff policy owner.
- Preserve the existing Google docstring convention and documented-source
  scope.
- Delete duplicate orchestration and its contract surface.

**Non-Goals:**

- No new rule family, threshold, framework, compatibility path, or product
  behavior.
- No change to test-source docstring policy.

## Decision

Extend the existing Ruff configuration with its pydocstyle convention and use
an explicit `--select D` invocation for the documented-source subset. The
single file owns syntax-level policy; Nox owns only execution scope. The
responsibility map points to that same file, and the contract test rejects a
second authority.

The alternative of retaining the smaller file was rejected because it gives
one tool two policy owners without an independent semantic boundary.

## Verification

Run the focused quality contract, `quick`, and `quality`; then execute the
exact-HEAD ETHOS proof before landing. Repository-wide search must find no
remaining reference to the retired file.
