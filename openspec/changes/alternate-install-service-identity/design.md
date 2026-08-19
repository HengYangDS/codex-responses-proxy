## Context

See `proposal.md`. Runtime configuration already owns portable data roots and
native supervision adapters already consume one context.

## Goals / Non-Goals

**Goals:**

- Make alternate-root installation physically independent from the canonical
  service.
- Keep one identity calculation and one lifecycle owner per platform.

**Non-Goals:**

- No change to the default service label, listener default, handoff protocol,
  payload inventory, provider routing, or client configuration.

## Decisions

1. Normalize the absolute installation root and hash it into a short deterministic
   suffix for alternate identities.
2. Keep the canonical public identity only for the canonical default data root.
3. Pass the context identity to every platform adapter instead of retaining a
   second legacy constant path.

## Risks / Trade-offs

- [An old temporary service can remain after an interrupted test] -> uninstall
  and recovery use the same derived identity and exact listener ownership.
- [A root path changes spelling] -> normalized absolute paths define identity;
  callers must treat a moved install as a new projection.

## Migration Plan

No migration is required for the default installation. Existing alternate test
services are removed by their derived identity before a new validation run.
Rollback is the existing transactional payload rollback; the production service
is never addressed by an alternate context.
