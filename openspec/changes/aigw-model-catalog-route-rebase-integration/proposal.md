## Why

The owned catalog-route lane was based on `74ca0eb`; `candidate/dev` then advanced
with the independent route-slot and SSE total-deadline fixes. Native replay detects
real overlaps in the changelog and route orchestrator. Replaying the catalog work
must retain both observable contracts rather than discarding either change.

## What Changes

- Rebase the closed `GET /<provider>/v1/models` contract onto the current candidate
  route behavior while preserving the candidate's route-local queue message,
  `Retry-After: 5`, and total stream-deadline behavior.
- Refresh the claim and chronicle bindings to the post-integration semantic tree,
  then repeat the required proof at the final work-lane head.
- Archive this integration carrier before candidate/accepted landing so the owned
  lane leaves no active OpenSpec residue.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `provider-portable-responses`: preserve the closed catalog route and the existing
  Responses overload/stream lifecycle requirements together on the current candidate
  base.

## Impact

Affected source is the request orchestrator and its release note, plus the
claim/evidence bindings. This changes neither AIGW configuration nor credentials,
installed payloads, conversation records, remote publication, or runtime lifecycle.
