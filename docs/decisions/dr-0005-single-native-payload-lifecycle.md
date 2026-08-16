# DR-0005: Maintain One Native Payload and Lifecycle Model

- Status: accepted
- Date: 2026-08-07

## Context

Parallel source, wheel, interpreter, compatibility-switch, and native payload
models create ambiguous ownership and unsafe rollback. Keeping readers or
migrations for retired layouts makes every lifecycle operation carry historical
states that the current product no longer needs.

## Decision

The installed product has one manifest-owned native bundle, one native
user-command link, and one native supervision lifecycle. The bundle exposes one
executable and carries its frozen runtime dependencies as adjacent
manifest-owned files. Installation accepts an empty target or one verified
current listener. The transaction commits the verified projection, prewarms
that exact executable before handoff, projects it through a platform-native
link, and records that exact path in the existing installed-state record. An
incompatible installation or foreign command target fails before mutation and
must be removed explicitly.

Rollback and recovery use exact current manifests, receipts, preimages, command
link ownership, and runtime identities. Source-level compatibility shims,
forwarding facades, wrappers, shell-profile mutation, retired layout readers,
and automatic migration from unsupported payloads are not product surfaces.

## Consequences

Lifecycle behavior has one owner and a smaller state space. A breaking payload
change may require explicit uninstall and reinstall rather than an implicit
migration. Historical release evidence remains immutable but does not constrain
the current runtime model.

## Revisit Trigger

Revisit only when a supported in-place migration is a current product
requirement with explicit ownership, failure semantics, and end-to-end proof.
