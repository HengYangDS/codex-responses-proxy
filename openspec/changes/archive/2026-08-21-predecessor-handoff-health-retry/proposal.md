## Why

A published `2.0.52` listener can transfer ownership to the exact `2.0.53`
successor, yet a failed post-commit health read outside the existing exception
allowlist is treated as terminal and rolls the upgrade back.

## What Changes

- Treat every failed health observation like the already retried socket and
  identity observations within the bounded health deadline.
- Preserve rollback after deadline expiry or non-transient validation failure.
- Add a regression at the health-probe boundary and reprove a real published
  predecessor-to-candidate native upgrade.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: Clarify that failed health reads are bounded observations
  during exact successor convergence.

## Impact

The protocol-v2 health observer, its focused tests, native release
compatibility proof, and runtime-upgrade contract are affected. Public CLI,
provider routing, credentials, the formal `8792` service, and AIGW are not.
