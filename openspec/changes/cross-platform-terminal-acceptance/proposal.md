## Why

The released proxy is healthy on macOS, but terminal product acceptance still
needs one explicit contract proving that installation, supervision, recovery,
and removal work through native artifacts on every supported operating system.
The repository binding must also remain consumable by the current governance
runtime so governance failure cannot obscure product readiness.

## What Changes

- Require native lifecycle acceptance on macOS, Linux, and Windows rather than
  treating cross-compilation or platform-adapter unit tests as equivalent proof.
- Require exact native-service ownership and residue-free teardown on every
  success and failure path.
- Make recovery distinguish healthy absence from invalid retained transaction
  evidence without changing or deleting unverifiable state.
- Repair the repository Commitment to the current strict schema without adding
  another governance path or changing Proxy product authority.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: require native install, status, recovery, and uninstall
  acceptance across every supported operating system.
- `product-interface`: extend the shared human/machine result model with
  precise recovery diagnostics for healthy, recoverable, and invalid states.

## Impact

The change affects the repository Commitment, lifecycle and native-supervisor
tests, release acceptance, CI projections, and narrowly related documentation.
It does not change provider routing, credentials, Codex configuration, private
conversation state, or AIGW ownership.
