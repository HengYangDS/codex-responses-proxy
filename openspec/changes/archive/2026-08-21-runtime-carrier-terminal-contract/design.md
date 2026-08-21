## Context

`2.0.55` exists only to cross the published `2.0.52` boundary. The formal `2.0.52 → 2.0.55` upgrade and a subsequent transactional reload succeeded, and the installed payload now contains a validated carrier. The bridge is therefore consumed; see `proposal.md`.

## Goals / Non-Goals

**Goals:**

- Restore one strict startup path for every private role.
- Remove the environment-to-carrier materializer and all bridge-only tests.
- Preserve a general current-release-to-successor native upgrade proof.
- Express the terminal state as a positive carrier contract.

**Non-Goals:**

- Supporting direct upgrades from releases that predate the carrier.
- Retaining a hidden emergency fallback or alternate runtime authority.
- Changing public commands, routes, credentials, or Forge topology.

## Decisions

### Require the carrier before every private role

`runtime_spec.activate(executable)` remains the sole activation operation. `_run_internal` invokes it identically for listener, handoff child, and watchdog. A missing or invalid carrier fails closed.

Alternative rejected: retain a handoff-only flag. It has no post-migration consumer and makes private-role semantics conditional on history.

### Delete migration mechanics, preserve forward lifecycle proof

Delete `_materialize_from_environment`, its parameter, and tests whose only purpose is the `2.0.52` discontinuity. Keep native lifecycle acceptance for the immediately preceding current release so ordinary forward upgrades remain executable product evidence.

Alternative rejected: retain the old fixture “for safety.” A test for an unsupported historical topology would turn retired debt into a permanent compatibility promise.

### Prefer positive structure over historical blacklists

Tests assert that all private roles call the same strict activation operation and that a valid carrier is present before startup. They do not enumerate retired fallback names or layouts.

Alternative rejected: add more forbidden-symbol checks. That encodes history rather than the desired product model and expands maintenance surface.

## Risks / Trade-offs

- Direct upgrade from pre-carrier releases becomes unsupported → `2.0.55` is the explicit migration release; users on older versions must first install it or perform a fresh install.
- Removing a fixture can hide unrelated upgrade regressions → retain current-to-successor installed CLI acceptance and the full native release suite.

## Migration Plan

1. Publish and formally install `2.0.55`; verify carrier, service, listener, reload, and no transaction residue.
2. Delete the bridge and release `2.0.56`.
3. Upgrade the formal runtime from `2.0.55` to `2.0.56` and repeat installed-product acceptance.
4. Roll back only by reinstalling the signed `2.0.55` asset through the transaction protocol; do not restore source fallback logic.
