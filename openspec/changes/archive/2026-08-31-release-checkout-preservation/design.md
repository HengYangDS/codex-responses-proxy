## Context

See [proposal.md](proposal.md). The publication path already receives the
expected release commit and validates the local annotated tag before any Forge
operation. The defect is that this read-side validation also executes `git
checkout --detach`, changing repository lifecycle state owned by the caller.

## Goals / Non-Goals

**Goals:**

- Make tag verification observational and deterministic.
- Preserve every caller-owned checkout surface on success and failure.
- Keep one shared release-source verifier for the command and GitHub adapter.

**Non-Goals:**

- Add a compensating branch restore, temporary checkout, or second repository.
- Change release assets, remote publication semantics, or runtime behavior.
- Retain the misleading mutating command as a compatibility alias.

## Decisions

Replace `prepare_checkout` with one private local-tag identity reader and remove
both fetch and detach. The caller already supplies a local signed release
object; publication only requires an annotated tag, dereferences its commit,
and compares it with the expected commit. Each Forge adapter separately
verifies its remote projection. The standalone command is deleted because the
existing release metadata command already owns CI tag-to-HEAD validation.

Use a real temporary Git repository regression for state preservation. Mock
call-count tests cannot prove symbolic-ref, index, and worktree invariants.

## Risks / Trade-offs

- **A hidden caller relies on detached HEAD** → repository search and release
  tests must prove there is no consumer; the release contract does not admit
  mutation as an output.
- **The local tag is absent** → fail closed before provider I/O; fetching remote
  identity remains the responsibility of the existing Forge evidence owner.
