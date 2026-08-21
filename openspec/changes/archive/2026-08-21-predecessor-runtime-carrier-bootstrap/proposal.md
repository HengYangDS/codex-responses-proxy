## Why

The published `2.0.52` installer can project a current native payload but does
not know that the successor requires `runtime-config.json`. The successor
handoff child therefore exits before protocol startup, even though the same
candidate appears healthy when its own CLI drives the upgrade.

## What Changes

- Make the published-predecessor test invoke the predecessor executable.
- Permit only a handoff child to materialize a missing runtime carrier from one
  complete predecessor environment or platform defaults.
- Keep all other private roles strict and retain `runtime-config.json` as the
  only persistent runtime authority.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: Define the bounded carrier bootstrap required to cross the
  published predecessor boundary without retaining a second authority.

## Impact

Private startup composition, runtime-carrier validation, published-predecessor
release proof, and the runtime-upgrade contract change. Public CLI, provider
routing, credentials, AIGW, and conversation state do not change.
