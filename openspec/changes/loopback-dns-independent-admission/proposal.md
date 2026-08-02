## Why

Loopback listener construction inherited an HTTP-server presentation lookup
that could block on local DNS before the socket began serving. A loopback-only
product must not make runtime admission depend on unrelated hostname services.

## What Changes

- Bind fresh loopback listeners without forward, reverse, or FQDN resolution.
- Derive listener identity from the address the kernel actually bound.
- Apply the same identity rule when adopting a handed-off listener.
- Enforce DNS-independent admission with a regression contract.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: subject=DNS-independent loopback listener admission;
  reuse=extend; change=modify; require both fresh and handoff-adopted listeners
  to become serviceable without DNS and to report their bound address;
  facet:lifecycle=runtime,upgrade,verification;
  facet:surface=source,test,docs,openspec;
  facet:authority=kernel,source,test,openspec.

## Out of Scope

- Changing the loopback-only network boundary, HTTP API, provider routing,
  retry, cooldown, or request-admission policy.
- Editing Codex JSONL, SQLite, transcripts, response-item data, or model metadata.
- Treating local proof as hosted CI, publication, installation, provider
  runtime, MCP, or original-conversation acceptance evidence.

## Impact

Listener startup and protocol-v2 socket handoff no longer depend on host DNS.
The HTTP surface, provider behavior, dependencies, and consumer configuration
remain unchanged.
