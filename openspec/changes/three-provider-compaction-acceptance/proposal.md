## Why

The released proxy now preserves Codex `compaction_trigger`, and unchanged
historical conversations have continued successfully through UCloud. The
canonical contract and route regression still fail to bind that exact control
item to all three governed services, and stale `UCloud/Azure` wording obscures
the real provider matrix.

## What Changes

- Name the provider matrix exactly as DMXAPI, UCloud, and AIHubMix.
- Require the same portable remote-compaction body to cross each of the three
  route namespaces without route-specific replay rewriting.
- Extend the route-level regression with the payload-free
  `{"type":"compaction_trigger"}` item while retaining fail-closed coverage
  for unknown future replay items.
- Record live acceptance only for upstreams that complete a fresh probe and
  retain DMXAPI as upstream-unverified while its quota is exhausted.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: bind the existing remote-compaction request
  control to the exact DMXAPI, UCloud, and AIHubMix route matrix.

## Out of Scope

- Changing the released request projector or admitting `context_compaction`.
- Editing Codex JSONL, SQLite, transcripts, titles, archives, or model
  metadata.
- Moving AIGW route, credential, or client-projection ownership into the proxy.
- Claiming DMXAPI upstream success while its quota remains exhausted.

## Impact

Only the canonical provider-portable contract, its route-level test, and
truth-bounded evidence change. No runtime dependency, endpoint, credential,
installation payload, or provider-specific implementation branch is added.
