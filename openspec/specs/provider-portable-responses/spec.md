# Provider-portable Responses

## Purpose

Provide one fail-closed Responses compatibility boundary that makes stored
Codex dialogue replayable across the governed DMXAPI, UCloud, and
AIHubMix routes without changing the conversation record itself.
## Requirements
### Requirement: Every Responses request is projected to a provider-portable form

Before upstream I/O, the proxy SHALL derive portability only from the current
request and the proved protocol grammar. It SHALL remove provider-bound
continuation state, stored-item references, replayed reasoning items, reasoning
ciphertext, encrypted agent or tool-output content, and the request for
`reasoning.encrypted_content`. It SHALL set `store=false` while leaving every
other provider-neutral generation setting unchanged. Canonical dialogue,
complete tool relationships, payload-free compaction controls, and supported
non-text agent content SHALL remain representable. Every bounded recovery
request SHALL preserve the same projection. No client configuration or
conversation store may be consulted or changed.

#### Scenario: A stored conversation changes provider

- **WHEN** a request contains `previous_response_id`, `conversation`,
  `prompt_cache_key`, an `rs_*` item, encrypted output, or another
  provider-owned continuation structure
- **THEN** none of that provider-bound state is sent to the selected upstream
- **AND** the upstream receives `store=false` with the remaining portable
  dialogue, complete tool history, and supported controls
- **AND** no AIGW setting, JSONL, SQLite, history item, or model metadata is
  read or modified.

#### Scenario: A new request has no replay state

- **WHEN** a valid Responses request contains only provider-neutral input and
  generation settings
- **THEN** the projection preserves those semantics, sets `store=false`, and
  does not manufacture a continuation identifier, stored item, or decrypted
  value.

#### Scenario: Codex requests remote compaction

- **WHEN** Codex appends the payload-free `{"type":"compaction_trigger"}`
  request control to portable dialogue
- **THEN** the projection preserves that exact control item for the upstream
  Responses compaction request
- **AND** any additional field on that control is rejected locally as an
  unproved request shape.

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

### Requirement: Paired empty tool results remain explicit

A correctly paired function or custom-tool result whose exact output is the
empty string SHALL retain its call kind and `call_id` and SHALL use one stable
plaintext empty-result marker in the outbound request copy. The exception SHALL
NOT apply to ordinary dialogue, missing or null output, or an invalid pair.

#### Scenario: A paired tool result is textually empty

- **WHEN** a valid function or custom-tool output follows its matching call and
  its exact result is the empty string
- **THEN** the outbound request retains the pair with the fixed empty-result
  marker
- **AND** it is not rejected as an empty dialogue message.

#### Scenario: Empty ordinary dialogue remains invalid

- **WHEN** a system, developer, user, assistant, or synthesized dialogue message
  contains no portable text
- **THEN** the proxy rejects the shape locally
- **AND** the empty-tool-result exception does not apply.

### Requirement: Unproved replay shapes fail closed

Malformed JSON, invalid input containers, unknown replay item types, unknown
content block types, orphaned or mismatched tool outputs, duplicate call/output
identities, and invalid required fields SHALL be rejected locally before any
upstream request is made. The error SHALL identify a bounded structural reason
without returning request text, credentials, or encrypted payloads.

#### Scenario: A future client introduces an unknown replay item

- **WHEN** the input list contains a replay item whose portable semantics are
  not defined by this capability
- **THEN** the proxy returns a local client error
- **AND** no configured provider receives the request.

#### Scenario: A tool output is not safely paired

- **WHEN** an output precedes its call, names an unknown `call_id`, duplicates
  an earlier output, or does not match the call kind
- **THEN** the request is rejected rather than silently deleting, reordering,
  or inventing tool history.

### Requirement: Provider routes admit only exact Responses and model-catalog targets

The listener SHALL expose provider-scoped loopback Responses targets and exact
read-only model-catalog targets for `dmxapi`, `ucloud`, and `aihubmix`. Each
namespace SHALL resolve only exact, lexically normalized
`POST /<provider>/v1/responses` targets or exact, lexically normalized
`GET /<provider>/v1/models` targets, with an optional query to the same
release-owned HTTPS upstream mapping. Model-catalog targets SHALL relay exactly
once without request or response projection, Responses admission, cooldown,
retry, or provider-policy recovery. Encoded path material, dot segments,
duplicate separators, lookalike suffixes, fragments, absolute targets, and
unrelated endpoints SHALL be rejected locally. A downstream request SHALL NOT
supply or override an upstream URL or host.

#### Scenario: AIGW selects each governed provider

- **WHEN** AIGW sends otherwise equivalent Requests traffic to
  `/dmxapi/v1/responses`, `/ucloud/v1/responses`, or
  `/aihubmix/v1/responses`
- **THEN** the proxy sends it only to the matching DMXAPI, UCloud, or
  AIHubMix HTTPS upstream
- **AND** credentials continue to come from the AIGW-managed client request.

#### Scenario: A caller uses an unknown namespace

- **WHEN** a request path does not match a control endpoint, one of the three
  canonical namespaces, or the bounded DMX migration route
- **THEN** the proxy rejects it locally
- **AND** it performs no remote network request.

#### Scenario: A consumer reads one provider model catalog

- **WHEN** it sends GET to `/dmxapi/v1/models`, `/ucloud/v1/models`, or
  `/aihubmix/v1/models`
- **THEN** the proxy relays exactly one GET to the matching provider
- **AND** it does not activate Responses projection, cooldown, retry, or
  recovery.

#### Scenario: A rejected route carries an unread body

- **WHEN** an unknown route or unsupported method is rejected before its body
  is consumed
- **THEN** the response closes the connection
- **AND** the unread body is not parsed as another request.

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

### Requirement: Streamed opaque output is not reintroduced into replay

For Responses event streams, the proxy SHALL remove provider-bound reasoning,
agent, and tool-output ciphertext before writing events downstream. If removal
would empty an agent or tool-output content list, the same omission-marker rule
SHALL apply. Malformed events SHALL be relayed unchanged only when no claimed
rewrite was partially applied.

#### Scenario: An upstream emits encrypted agent content

- **WHEN** a streamed output item contains plaintext plus encrypted agent or
  tool-output blocks
- **THEN** downstream receives the plaintext and no effective encrypted block
- **AND** later Codex replay cannot send that ciphertext to another provider.

### Requirement: Non-stream Responses are projected before commitment

Successful non-stream Responses SHALL be buffered within an eight-MiB limit
before downstream HTTP commitment, required to be a valid `completed` or
`incomplete` Response JSON document, and projected with the same
provider-ciphertext rules as SSE. Empty, truncated, oversized, malformed,
failed, or otherwise non-terminal HTTP 2xx bodies SHALL produce a local
retryable failure without committing partial upstream bytes.

#### Scenario: A successful JSON response contains provider ciphertext

- **WHEN** a terminal non-stream Response contains visible output plus opaque
  reasoning, agent, or tool-output ciphertext
- **THEN** downstream receives the visible output without the ciphertext
- **AND** the response is committed with a correct bounded content length.

#### Scenario: HTTP 2xx does not contain a proved terminal Response

- **WHEN** the body is empty, truncated, malformed, failed, in progress, or
  missing a terminal status
- **THEN** downstream receives a local retryable failure
- **AND** no upstream success status or partial body has been committed.

### Requirement: Request-changing recovery uses structured errors

Recovery that changes the projected request SHALL be admitted only from a
bounded structured error contract. Human-readable message text alone SHALL NOT
activate compaction, dialogue recovery, or schema fallback.

#### Scenario: Error prose contains a known phrase

- **WHEN** a structured error has an unrelated type or code but its message
  mentions `response_failed`, `request blocked`, or another recovery phrase
- **THEN** the proxy relays or classifies it without changing replay.

### Requirement: Conversation state remains owned by Codex

The compatibility path SHALL NOT edit Codex JSONL, SQLite, transcript history,
archived conversations, hidden resume pointers, or per-conversation model
metadata. Success SHALL require an unchanged original conversation to complete
multiple turns after the provider sequence DMXAPI, UCloud, AIHubMix, and
DMXAPI again.

#### Scenario: The integrated fix is accepted

- **WHEN** the released proxy and AIGW projections are installed and the same
  original conversation completes at least two turns on each leg of
  DMXAPI to UCloud to AIHubMix to DMXAPI
- **THEN** no turn reports missing `rs_` items, encrypted-content decode or
  decrypt failure, or proxy-generated empty-response 503
- **AND** acceptance evidence confirms the session files and model metadata
  were not modified by the repair.

### Requirement: Client endpoint ownership is external

The proxy SHALL expose provider-scoped loopback Responses endpoints without
reading, writing, backing up, or restoring AIGW or client configuration. It
SHALL NOT execute an AIGW command or persist consumer route state.

#### Scenario: A consumer selects a provider endpoint

- **WHEN** AIGW or another client selects `/dmxapi/v1`, `/ucloud/v1`, or
  `/aihubmix/v1` through its own control plane
- **THEN** the proxy serves that data-plane request without depending on the
  consumer package, configuration path, credential store, or projection model.

#### Scenario: The proxy is installed or removed

- **WHEN** installation, status, reload, or uninstall runs
- **THEN** only the proxy's released payload, product-owned state, listener,
  and native supervision are observed or mutated
- **AND** consumer endpoint configuration is unchanged.

### Requirement: Successful non-stream Responses are projected atomically

The proxy SHALL buffer a successful non-stream Responses body within one fixed
eight-MiB limit before downstream commitment, remove provider-bound reasoning,
agent, and tool-output ciphertext, reject any unknown residual ciphertext
carrier, and emit only a structurally proved completed or incomplete Response
JSON document. Empty, truncated, oversized, malformed, or semantically
incomplete successful bodies SHALL fail locally without committing partial
upstream bytes.

#### Scenario: A non-stream response contains provider ciphertext

- **WHEN** an upstream JSON Response contains visible output and encrypted
  reasoning, agent, or tool-output content
- **THEN** downstream receives the visible output and no effective ciphertext
- **AND** later replay cannot carry that ciphertext to another provider.

#### Scenario: A successful response body is not complete and proved

- **WHEN** an upstream returns HTTP 2xx with an empty, truncated, malformed, or
  non-terminal Responses body
- **THEN** the proxy returns a bounded retryable local failure
- **AND** no partial body or successful upstream status is committed downstream.

#### Scenario: A successful response exceeds the integrity bound

- **WHEN** an upstream HTTP 2xx body exceeds eight MiB before terminal JSON is
  proved
- **THEN** the proxy returns a bounded retryable local failure
- **AND** no upstream bytes are committed as success.

#### Scenario: An unknown output carrier retains ciphertext

- **WHEN** known projection rules leave any `encrypted_content` key in the
  terminal JSON document
- **THEN** the proxy fails closed rather than forwarding an unproved carrier.

### Requirement: Responses admission is closed at the HTTP boundary

Every POST Responses request SHALL pass through fail-closed request projection,
including a zero-length body. Provider-scoped routes SHALL resolve only exact,
lexically normalized `/v1/responses` targets with an optional query.

#### Scenario: A caller sends an empty Responses request

- **WHEN** a POST Responses request has no body
- **THEN** the proxy rejects it locally as invalid JSON
- **AND** no configured provider receives the request.

#### Scenario: A caller sends an ambiguous route suffix

- **WHEN** the route contains dot segments, encoded path material, duplicate
  separators, a lookalike suffix, or a non-Responses endpoint
- **THEN** the proxy rejects it locally
- **AND** it does not construct or contact an upstream URL.

### Requirement: Provider wire differences are isolated

The provider manifest MAY select one optional pure wire-policy module. Core
transport SHALL depend only on that policy contract and SHALL NOT branch on a
provider name. A provider with no wire difference SHALL require only one
secret-free manifest entry. A policy MUST NOT perform HTTP dispatch, retries,
credential access, host discovery, filesystem access, runtime mutation,
lifecycle operations, or client configuration.

#### Scenario: A new ordinary provider is added

- **WHEN** a synthetic provider's Responses wire behavior matches the
  provider-neutral core
- **THEN** setup requires only its declarative manifest record
- **AND** no listener, relay, lifecycle, CLI, release, service, consumer,
  replay, or registry provider-name branch is added.

#### Scenario: A provider has a proved special wire contract

- **WHEN** executable fixtures prove a distinct request, response, or error
  contract
- **THEN** one manifest-selected policy implements only that transformation or
  classification
- **AND** every higher layer continues to depend on the policy contract rather
  than provider identity.

### Requirement: Recovery classifiers use structured provider errors

Any recovery that changes the request body SHALL be triggered only by a bounded
structured error contract. Incidental human-readable message text SHALL NOT be
sufficient to activate semantic recovery.

#### Scenario: Ordinary error prose contains a recovery phrase

- **WHEN** an upstream error message contains a known phrase but its structured
  type and code do not match the recovery contract
- **THEN** the proxy relays or classifies the error without changing replay.

### Requirement: Provider rate limits do not multiply across retry layers

For an upstream HTTP 429, the proxy SHALL make no additional upstream attempt
for the current client request. It SHALL relay the first upstream status, body,
and eligible non-hop-by-hop headers unchanged, SHALL NOT sleep before that
relay, and SHALL record a bounded provider-scoped cooldown. A valid upstream
`Retry-After` SHALL determine the cooldown up to five minutes; a value above
that bound SHALL be capped, while an omitted, invalid, zero, or expired value
SHALL use a five-second fallback. The proxy SHALL NOT infer or configure an
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

### Requirement: Active provider cooldown deadlines do not move backward

For one cooldown key, a repeated or concurrent failure SHALL NOT replace a
still-active deadline with an earlier deadline. The proxy SHALL retain the later
of the current and newly computed deadlines under the existing synchronized
cache owner. It SHALL continue to purge expired entries, bound cache capacity,
and isolate unrelated provider and request-fingerprint keys.

#### Scenario: A shorter rate limit follows a longer active instruction

- **WHEN** one provider has an active 300-second cooldown and a later failure
  computes a five-second cooldown before the first deadline expires
- **THEN** the stored deadline remains the original later deadline
- **AND** upstream traffic for that provider is not reopened by the shorter
  overlapping failure.

#### Scenario: Another key receives a shorter deadline

- **WHEN** an unrelated provider or request fingerprint records a shorter
  cooldown
- **THEN** its deadline is stored independently
- **AND** the longer key is neither shortened nor copied across the boundary.

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
