## Context

See `proposal.md` for motivation. The product already has one Python lifecycle
core and thin launchd, systemd-user, and Task Scheduler adapters. Current hosted
jobs build native artifacts, but terminal acceptance must prove the same public
journey and ownership invariants rather than infer portability from source tests.

## Goals / Non-Goals

**Goals:**

- Keep one lifecycle state machine and one runtime carrier across platforms.
- Exercise native artifacts through public install, status, recover, and
  uninstall commands on macOS, Linux, and Windows.
- Prove exact service and process ownership, including failure teardown.
- Keep repository governance repair separate from product authority.

**Non-Goals:**

- Managing provider credentials or client configuration.
- Modifying Codex history, metadata, or private state.
- Introducing a portable supervisor framework above native service managers.
- Retaining compatibility paths for unsupported historical state.

## Decisions

### Keep native service managers behind one product contract

The lifecycle core remains authoritative. Platform adapters project that
contract into launchd, systemd user services, and Task Scheduler. This retains
native operational behavior without creating three lifecycle implementations.

Alternative rejected: a cross-platform supervisor dependency. It would add an
authority layer while still relying on platform-specific registration and
process semantics underneath.

### Prove portability with native black-box journeys

Each supported platform builds its own self-contained artifact and exercises
the same public lifecycle state sequence. Unit tests and cross-compilation are
necessary but cannot substitute for native service-manager behavior.

### Treat host resources as exact owned projections

Creation and teardown use the same resolved service identifier, projection
path, executable identity, and process generation. Cleanup never matches a
name prefix and never touches the canonical service while testing an isolated
installation.

### Keep recovery fail-closed and state-specific

No transaction is a successful no-op. A valid retained transaction is
recoverable. Invalid or ambiguous retained bytes produce a precise diagnostic
and remain unchanged for forensic inspection. Recovery never guesses intent.

### Migrate the repository Commitment in place

The tracked repository Commitment adopts the current strict schema and remains
the sole repository-level contract. No compatibility reader, duplicate carrier,
or ETHOS-owned product semantic is introduced.

## Risks / Trade-offs

- Native service tests can leak host state if teardown is not exact. Mitigation:
  compare exact pre/post inventories and prove owned process termination.
- Hosted runners can be unavailable. Mitigation: report infrastructure absence
  separately; do not weaken product acceptance or block independent platforms.
- A lifecycle failure can disrupt the formal local service. Mitigation: use
  isolated roots and service identities until a signed release is accepted.

## Migration Plan

1. Repair and validate the repository Commitment.
2. Add or tighten native lifecycle acceptance and failure regressions.
3. Run focused tests, strict quality, the Python matrix, and native release
   acceptance without touching the formal service.
4. Promote one signed product SHA through independent GitHub and GitLab
   projections, then transactionally upgrade and verify the formal runtime.
5. Remove the absorbed work lane, proposal refs, and temporary evidence after
   exact equivalence and remote convergence are proven.
