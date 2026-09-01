## Context

See `proposal.md`. `request.py` already owns request-local structural
validation and pair tracking; the defect is incomplete validation inside that
existing boundary, not a missing subsystem.

## Goals / Non-Goals

**Goals:**

- Make the accepted Codex local-shell schema explicit and fail closed.
- Require every removed local-shell call to have one matching removed output.
- Preserve one item-classification authority and one request projection pass.

**Non-Goals:**

- Forward local shell execution to third-party providers.
- Read or rewrite conversation storage.
- Add a schema framework, compatibility layer, or second normalization pass.

## Decisions

1. Extend the existing request projector rather than introduce a model layer.
   The grammar is small, request-local, and already owned here; another runtime
   dependency or parallel validator would add more authority than value.
2. Validate the upstream Codex closed shape: statuses are `completed`,
   `in_progress`, or `incomplete`; an `exec` action admits only `type`,
   `command`, `timeout_ms`, `working_directory`, `env`, and `user`, with their
   declared scalar and collection types.
3. Track removed local-shell calls as pending until a matching output is seen,
   then reject any pending call at the end of the existing single pass.

## Risks / Trade-offs

- [A newer Codex schema adds a field] -> The proxy rejects it as schema drift
  until its semantics are deliberately admitted, preventing silent corruption.
- [Malformed history previously appeared to work] -> It now fails locally with
  a bounded reason instead of sending incomplete dialogue upstream.
