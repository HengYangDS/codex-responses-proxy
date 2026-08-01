## Why

The process-local runtime state module owned unrelated logging, telemetry,
admission, drain, and provider cooldown behavior. Replay normalization also
encoded metrics into a diagnostic string which telemetry parsed back into
data. These hidden contracts made the physical package structure misleading.

## What Changes

- Give admission/drain, telemetry, safe logging, and transport cooldown one
  concrete module owner each.
- Return an immutable structured replay result and derive diagnostics only at
  the presentation boundary.
- Make every caller import the defining module directly and retire the mixed
  runtime state module without a compatibility facade.
- Enforce the module ownership and package declaration contract in tests and
  the repository architecture gate.
- State dual-Forge identity truth precisely: provider-native commits may have
  different object ids while preserving verified tree, message, date, and
  parent-topology correspondence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: subject=runtime semantic ownership and Forge parity;
  reuse=extend; change=modify; replace the mixed runtime owner and prose metrics
  protocol with concrete owners and structured data while keeping publication
  identity-aware and append-only;
  facet:lifecycle=runtime,quality,release;
  facet:surface=source,test,docs,openspec,evidence;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Editing Codex JSONL, SQLite, transcript history, response-item data, or model metadata.
- Changing provider routes, credentials, upstream origins, or provider-specific wire policy.
- Adding a compatibility facade for removed internal APIs.
- Claiming hosted CI, publication, installation, provider runtime, MCP, or original-session
  acceptance from local source proof.

## Impact

HTTP behavior, provider routes, and Codex-owned conversation data remain
unchanged. The released payload inventory changes only to replace the retired
mixed module with its concrete owners. The change affects internal APIs,
quality contracts, documentation, and release-history verification.
