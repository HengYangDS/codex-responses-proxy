## MODIFIED Requirements

### Requirement: Every Responses request is projected to a provider-portable form

Before upstream I/O, the proxy SHALL derive portability only from the current
request and the proved protocol grammar. It SHALL remove provider-bound
continuation state, stored-item references, replayed reasoning items, and
encrypted replay content. It SHALL set `store=false` and remove any request for
`reasoning.encrypted_content` while leaving provider-neutral generation settings
unchanged.

#### Scenario: A stored conversation changes provider

- **WHEN** a request contains `previous_response_id`, `conversation`,
  `prompt_cache_key`, an `rs_*` item, encrypted output, or another
  provider-owned continuation structure
- **THEN** none of that provider-bound state is sent to the selected upstream
- **AND** the upstream receives `store=false` with the remaining portable
  dialogue, complete tool history, and supported controls
- **AND** no client setting, JSONL, SQLite, history item, or model metadata is
  read or modified.

#### Scenario: A new request has no replay state

- **WHEN** a valid Responses request contains only provider-neutral input and
  generation settings
- **THEN** the projection preserves those semantics, sets `store=false`, and
  does not manufacture a continuation identifier, stored item, or decrypted
  value.

#### Scenario: Portable content is projected

- **WHEN** canonical dialogue, complete tool relationships, payload-free
  compaction controls, or supported non-text agent content is present
- **THEN** the projection keeps it representable
- **AND** every bounded recovery preserves the same projection
- **AND** no client configuration or conversation store is consulted or changed.

#### Scenario: Codex requests remote compaction

- **WHEN** Codex appends the payload-free `{"type":"compaction_trigger"}`
  request control to portable dialogue
- **THEN** the projection preserves that exact control item for the upstream
  Responses compaction request
- **AND** any additional field on that control is rejected locally as an
  unproved request shape.

#### Scenario: A conversation changes providers repeatedly

- **WHEN** a subsequent request switches among UCloud, DMXAPI, and AIHubMix
- **THEN** the outbound request uses `store=false`
- **AND** no `rs_*`, provider item identifier, or unproved provider-specific replay structure crosses the provider boundary
- **AND** portable user and agent content remains replayable.

### Requirement: Portable dialogue and tool relationships are preserved

The proxy SHALL preserve textual system, developer, user, and assistant
dialogue; agent author, recipient, and phase context; and complete
function/custom-tool call-output pairs. Assistant and synthesized-agent history
SHALL use provider-neutral Easy Input Message strings. System, developer, user,
and tool-output lists SHALL use input-content grammar. Provider IDs, statuses,
annotations, and opaque metadata SHALL NOT be required.

#### Scenario: Text and paired calls are replayed

- **WHEN** a request contains text messages, an agent message, a function call
  and output, and a custom-tool call and output
- **THEN** the upstream receives equivalent role-valid portable text and both
  complete call-output pairs
- **AND** every output retains the matching `call_id` and call kind.

#### Scenario: Assistant content is normalized for replay

- **WHEN** an assistant message or projected agent message contains
  `input_text`, `output_text`, or refusal content from stored history
- **THEN** its portable assistant representation uses a deterministic string
  that preserves the visible text and phase
- **AND** it does not require output-item ID, status, annotation, or typed
  output content from the prior provider.

#### Scenario: Instruction and user content remain input

- **WHEN** a system, developer, or user message contains typed text from stored
  history
- **THEN** its portable representation uses `input_text`
- **AND** no assistant-only output block is emitted for that role.

#### Scenario: An agent or tool output has only opaque ciphertext

- **WHEN** removing encrypted content would otherwise leave an agent message or
  tool output empty
- **THEN** the proxy inserts a stable plaintext omission marker using the
  assistant string carrier or tool-output input grammar
- **AND** it does not claim to have decrypted or reconstructed the omitted
  result.

#### Scenario: Classified DMX retry preserves the projected bytes

- **WHEN** the normal provider-portable request receives the exact classified
  DMX empty-response error
- **THEN** the proxy retries the current projected attempt bytes exactly once
- **AND** it does not rebuild replay, restore an older request body, or recreate
  a provider-bound assistant typed-block shape.

#### Scenario: Classified DMX retry retains replayable input images

- **WHEN** the normal portable request contains a validated remote
  `input_image` in system, developer, user, or tool-output input content and
  receives the exact classified DMX empty-response error
- **THEN** the byte-identical retry preserves that image on input grammar
- **AND** it does not turn valid non-text input into a local exhausted 503.

#### Scenario: Recovery contains non-text agent content

- **WHEN** a recoverable response contains valid non-text agent items
- **THEN** recovery preserves their provider-portable semantic representation
- **AND** does not fabricate text or require provider-bound identifiers.

### Requirement: Provider-specific recovery is route-scoped

The exact DMXAPI HTTP 477 `empty_response` recovery and cooldown SHALL apply
only to the DMXAPI route. A failure or cooldown key from DMXAPI SHALL NOT block,
rewrite, or classify a UCloud or AIHubMix request. Generic transient and
schema recovery MAY remain shared only where its trigger is provider-neutral
and exact.

#### Scenario: DMXAPI enters empty-response cooldown

- **WHEN** a DMXAPI request exhausts its exact HTTP 477 recovery and the same
  portable body is then sent to UCloud or AIHubMix
- **THEN** the other provider request is attempted normally
- **AND** no DMXAPI cooldown response is reused across the route boundary.

#### Scenario: A non-DMX provider returns HTTP 477

- **WHEN** UCloud or AIHubMix returns HTTP 477
- **THEN** the proxy does not apply the DMXAPI `empty_response` policy unless
  the request was routed to DMXAPI and the exact DMX error contract matched.

#### Scenario: DMXAPI exhausts empty-response recovery

- **WHEN** DMXAPI yields the exact classified empty response through the bounded retry policy
- **THEN** the proxy emits a typed terminal error only after the budget is exhausted
- **AND** UCloud and AIHubMix remain independently usable.

### Requirement: Provider rate limits do not multiply across retry layers

For an upstream HTTP 429, the proxy SHALL make no additional upstream attempt
for the current client request. It SHALL relay the first upstream status, body,
and eligible non-hop-by-hop headers unchanged without sleeping. It SHALL record
a bounded provider-scoped cooldown and SHALL NOT infer or configure an
undocumented provider quota.

#### Scenario: A provider returns a rate limit

- **WHEN** one provider Responses attempt returns HTTP 429
- **THEN** the proxy relays that exact status, body, and eligible headers after
  exactly one upstream call
- **AND** it performs neither the generic proxy retry sleep nor another upstream
  request for that client attempt.

#### Scenario: The provider supplies bounded retry timing

- **WHEN** a provider returns HTTP 429 with valid delta-seconds or HTTP-date
  `Retry-After` no greater than five minutes
- **THEN** later Responses for only that provider receive local HTTP 429 until
  the interpreted process-local deadline expires
- **AND** the original response retains the provider's exact header.

#### Scenario: The provider supplies no usable retry timing

- **WHEN** a provider omits `Retry-After` or supplies an invalid, zero, or
  expired value
- **THEN** later Responses for that provider receive local HTTP 429 for the
  five-second fallback without opening an upstream connection
- **AND** another configured provider remains unaffected.

#### Scenario: The provider supplies excessive retry timing

- **WHEN** a provider supplies a positive `Retry-After` above five minutes
- **THEN** the process-local cooldown is capped at five minutes.

#### Scenario: One provider is rate-limited

- **WHEN** UCloud, DMXAPI, or AIHubMix records an active provider-scoped cooldown
- **THEN** no other provider inherits that cooldown or loses ordinary concurrency
- **AND** client-owned per-session concurrency remains outside the proxy.

### Requirement: Ordinary concurrency remains outside the proxy

The proxy SHALL NOT serialize a provider route, queue ordinary traffic, or own
a fixed or configurable ordinary-request concurrency ceiling. Codex owns
per-session concurrency and each provider owns its actual quota. Each request
SHALL check that provider's cooldown and the lifecycle drain barrier before
remote I/O. HTTP 429 SHALL remain terminal for the current request and SHALL NOT
introduce an upstream retry. Active-request accounting exists only for
lifecycle handoff and observation.

#### Scenario: Concurrent requests target one provider route

- **WHEN** two Responses requests overlap on the same configured provider route
- **THEN** neither request waits in a proxy-owned concurrency queue
- **AND** both may perform provider I/O unless a provider cooldown or lifecycle
  drain is active.

#### Scenario: Different provider routes overlap

- **WHEN** Responses requests overlap on two different configured provider
  routes
- **THEN** both routes can perform provider I/O concurrently
- **AND** neither a route-level nor process-wide ordinary admission slot or
  queue exists.

#### Scenario: One request establishes cooldown

- **WHEN** a later request arrives after a preceding request recorded a
  provider rate-limit cooldown
- **THEN** the later request receives the existing local HTTP 429 response
- **AND** the proxy makes no upstream call for that later request.

#### Scenario: Lifecycle drain closes admission

- **WHEN** a transactional reload or shutdown activates the drain barrier
- **THEN** new Responses receive the bounded local draining response
- **AND** active-request accounting remains available for safe handoff without
  becoming an ordinary traffic limit.
