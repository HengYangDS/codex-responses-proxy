## Context

The transaction root is the sole recovery carrier. Its current reader is
fail-closed, but it delegates parsing to a generic JSON helper whose message
does not identify which invariant failed. The native adapters already consume
one `RuntimeContext`; lifecycle tests must keep using that same resolved
context for creation, observation, and teardown.

## Goals / Non-Goals

**Goals:**

- Preserve one transaction authority while making every invalid carrier state
  mutually exclusive and actionable.
- Preserve invalid bytes exactly; diagnostics remain read-only.
- Keep native service creation and teardown bound to the same service identity,
  carrier path, executable, and process roles.
- Prove isolated lifecycle tests leave the formal service unchanged.

**Non-Goals:**

- No compatibility reader or automatic repair for historical journal schemas.
- No second recovery command, migration state machine, or forensic store.
- No change to provider behavior, client configuration, or formal port `8792`.

## Decisions

### Classify at the journal owner

`lifecycle.state` owns journal bytes and schema, so it also owns carrier
classification. It uses the standard JSON parser and the existing canonical
encoder; no new validation framework or parallel model is introduced. The
reader distinguishes filesystem shape, syntax, canonical encoding, schema
version, and field validity before returning the current journal mapping.

### Preserve one public error boundary

`transaction.recover` continues translating all invalid journal observations
to `RecoveryStateError`. Human and JSON output therefore retain one stable
error code and one safe `status --json` next action while exposing a precise
message. Invalid state is never deleted or rewritten.

### Treat native services as exact owned projections

The `RuntimeContext` used to create a native service remains the sole source of
its service identifier and carrier path. Test teardown calls the product's
exact uninstall adapter with that same context, proves owned processes are
gone, and compares host projection sets before and after the lifecycle.

## Verification

Start with journal classification regressions, then run focused lifecycle and
CLI tests. Run native lifecycle acceptance only after the source behavior is
green, and compare the exact formal service, listener, plist, and noncanonical
service inventories before and after.
