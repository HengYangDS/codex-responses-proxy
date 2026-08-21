## Context

An isolated upgrade using the official `v2.0.52` and `v2.0.53` macOS assets
proved this sequence:

```text
2.0.52 idle
-> 2.0.52 preparing
-> 2.0.53 serving with exact PID and payload identity
-> 2.0.52 rolled back
```

The predecessor logged `handoff_commit_failed phase=health exception=error`.
The released binary does not expose the exception module, so its exact concrete
type is unproved; the important owner boundary is already known: it escaped the
health observer's explicit exception allowlist after the exact successor had
begun serving.

## Goals / Non-Goals

**Goals:**

- Keep the exact successor identity as the only success condition.
- Retry failed read-only observations until one deadline.
- Preserve bounded rollback and secret-free failure logging.

**Non-Goals:**

- No protocol version, public CLI, provider, supervisor, or timeout model change.
- No catch-all exception suppression.
- No mutation of the formal listener during development proof.

## Decision

Treat `Exception` from the read-only health observation as one absent
observation. The loop has a single bounded deadline and exact identity remains
the only success condition; `BaseException` control flow is not intercepted.
This avoids an incomplete exception taxonomy and a parallel retry path while
remaining fail-safe.

## Risks / Trade-offs

- [Persistent protocol failure consumes the deadline] -> Required fail-safe
  behavior; the bounded deadline still triggers rollback.
- [A programming defect inside the observer is retried] -> It remains bounded
  by one deadline and cannot be accepted without exact identity; terminal
  non-convergence still rolls back.
