## MODIFIED Requirements

### Requirement: Every Responses request is projected to a provider-portable form

Before upstream I/O, the proxy SHALL remove provider-bound continuation state,
stored-item references, replayed reasoning items, reasoning ciphertext, and
encrypted agent or tool-output content from each Responses request. The
projection SHALL also remove the request for `reasoning.encrypted_content` and
SHALL set `store=false` while leaving every other provider-neutral generation
setting unchanged. Every bounded recovery request SHALL preserve `store=false`.

#### Scenario: A stored conversation changes provider

- **WHEN** a request contains `previous_response_id`, `conversation`,
  `prompt_cache_key`, provider-issued item identifiers, reasoning items, or
  encrypted replay blocks from an earlier provider
- **THEN** none of that provider-bound state is sent to the selected upstream
- **AND** the current request is carried by the remaining portable dialogue and
  tool history
- **AND** the upstream receives `store=false` and no provider-issued response,
  conversation, or item identity.

#### Scenario: A new request has no replay state

- **WHEN** a valid Responses request contains only provider-neutral input and
  generation settings
- **THEN** the projection preserves those semantics, sets `store=false`, and
  does not manufacture a continuation identifier, stored item, or decrypted
  value.

#### Scenario: Codex requests remote compaction through each provider route

- **WHEN** Codex appends the payload-free
  `{"type":"compaction_trigger"}` request control to portable dialogue and
  AIGW selects DMXAPI, UCloud, or AIHubMix
- **THEN** the proxy preserves that exact control item in the request sent
  through each selected provider namespace
- **AND** otherwise equivalent projected bodies are identical across the three
  provider routes
- **AND** any additional field on that control is rejected locally as an
  unproved request shape.

### Requirement: Provider routes admit only exact Responses targets

The listener SHALL expose provider-scoped loopback Responses targets for
`dmxapi`, `ucloud`, and `aihubmix`. Each namespace SHALL resolve only exact
`/<provider>/v1/responses` targets with an optional query to its release-owned
HTTPS upstream mapping. Encoded path material, dot segments, duplicate
separators, lookalike suffixes, fragments, absolute targets, and unrelated
endpoints SHALL be rejected locally. A downstream request SHALL NOT supply or
override an upstream URL or host.

#### Scenario: AIGW selects each governed provider

- **WHEN** AIGW sends otherwise equivalent Responses traffic to
  `/dmxapi/v1/responses`, `/ucloud/v1/responses`, or
  `/aihubmix/v1/responses`
- **THEN** the proxy sends it only to the matching DMXAPI, UCloud, or AIHubMix
  HTTPS upstream
- **AND** credentials continue to come from the AIGW-managed client request.

#### Scenario: A caller uses an unknown namespace

- **WHEN** a request path does not match a control endpoint, one of the three
  canonical namespaces, or the bounded DMX migration route
- **THEN** the proxy rejects it locally
- **AND** it performs no remote network request.

### Requirement: Provider-specific recovery is route-scoped

The exact DMXAPI HTTP 477 `empty_response` recovery and cooldown SHALL apply
only to the DMXAPI route. A failure or cooldown key from DMXAPI SHALL NOT block,
rewrite, or classify a UCloud or AIHubMix request. Generic transient and schema
recovery MAY remain shared only where its trigger is provider-neutral and
exact.

#### Scenario: DMXAPI enters empty-response cooldown

- **WHEN** a DMXAPI request exhausts its exact HTTP 477 recovery and the same
  portable body is then sent to UCloud or AIHubMix
- **THEN** the other provider request is attempted normally
- **AND** no DMXAPI cooldown response is reused across the route boundary.

#### Scenario: A non-DMX provider returns HTTP 477

- **WHEN** UCloud or AIHubMix returns HTTP 477
- **THEN** the proxy does not apply the DMXAPI `empty_response` policy unless
  the request was routed to DMXAPI and the exact DMX error contract matched.

### Requirement: Conversation state remains owned by Codex

The compatibility path SHALL NOT edit Codex JSONL, SQLite, transcript history,
archived conversations, hidden resume pointers, or per-conversation model
metadata. Provider portability SHALL be accepted only when the same portable
request is proven across DMXAPI, UCloud, and AIHubMix and an unchanged original
conversation completes multiple turns through every live upstream used for
acceptance. When an upstream is unavailable because of an externally verified
account or quota condition, that provider leg MAY be accepted locally for route
and projection behavior, but its live upstream result SHALL remain explicitly
unverified until a later successful probe.

#### Scenario: The integrated fix is accepted

- **WHEN** the released proxy and AIGW projections are installed, the same
  original conversation completes at least two turns through each available
  upstream selected for acceptance, and all three provider routes pass the same
  local portable-request projection
- **THEN** no turn reports missing `rs_` items, encrypted-content decode or
  decrypt failure, or proxy-generated empty-response 503
- **AND** acceptance evidence confirms the session files and model metadata
  were not modified by the repair
- **AND** any provider excluded from live acceptance because of account or
  quota state is named as upstream-unverified rather than reported as a live
  success.
