## MODIFIED Requirements

### Requirement: Provider switching is stateless

The proxy SHALL send Responses requests with upstream storage disabled and
SHALL reject or normalize provider-bound replay structures before they reach a
different provider.

#### Scenario: A conversation changes providers

- **WHEN** a subsequent request is routed to UCloud, DMXAPI, or AIHubMix instead of the prior provider
- **THEN** the outbound request uses `store=false`
- **AND** no `rs_*`, provider item identifier, or unproved provider-specific replay structure crosses the provider boundary
- **AND** portable user and agent content remains replayable.

### Requirement: Upstream failure recovery preserves agent semantics

Empty or non-text upstream results SHALL be handled through bounded,
provider-aware recovery without fabricating text or losing valid agent content.

#### Scenario: DMXAPI returns an empty response

- **WHEN** DMXAPI yields an empty upstream response within the configured retry budget
- **THEN** the proxy retries only within that bounded policy
- **AND** emits a typed terminal error only after the budget is exhausted
- **AND** a peer provider remains independently usable.

#### Scenario: Recovery contains non-text agent content

- **WHEN** a recoverable response contains valid non-text agent items
- **THEN** recovery preserves their portable semantic representation
- **AND** does not require provider-bound identifiers.

### Requirement: Backpressure is provider-scoped

Rate-limit state SHALL be isolated by provider and SHALL respect the client's
per-conversation concurrency policy without imposing one low global bottleneck.

#### Scenario: One provider returns 429

- **WHEN** UCloud rate-limits a request
- **THEN** only UCloud's bounded retry and concurrency state is reduced
- **AND** DMXAPI and AIHubMix continue under their own limits.
