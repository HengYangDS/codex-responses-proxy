# Provider-portable Responses

## Purpose

Provide one fail-closed Responses compatibility boundary that makes stored
Codex dialogue replayable across the governed DMXAPI, UCloud/Azure, and
AIHubMix routes without changing the conversation record itself.
## Requirements
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
  tool history.
- **AND** the upstream receives `store=false` and no provider-issued response,
  conversation, or item identity.

#### Scenario: A new request has no replay state

- **WHEN** a valid Responses request contains only provider-neutral input and
  generation settings
- **THEN** the projection preserves those semantics, sets `store=false`, and
  does not manufacture a continuation identifier, stored item, or decrypted
  value.

#### Scenario: Codex requests remote compaction

- **WHEN** Codex 0.146 or later appends the payload-free
  `{"type":"compaction_trigger"}` request control to portable dialogue
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

### Requirement: Three canonical routes use a fixed upstream allowlist

The listener SHALL expose provider-scoped loopback namespaces for `dmxapi`,
`ucloud`, and `aihubmix`. Each namespace SHALL resolve only to its release-owned
HTTPS upstream mapping, strip only its own route prefix, and forward the
remaining path and query. A downstream request SHALL NOT supply or override an
upstream URL or host.

#### Scenario: AIGW selects each governed provider

- **WHEN** AIGW sends otherwise equivalent Requests traffic to
  `/dmxapi/v1`, `/ucloud/v1`, or `/aihubmix/v1`
- **THEN** the proxy sends it only to the matching DMXAPI, UCloud/Azure, or
  AIHubMix HTTPS upstream
- **AND** credentials continue to come from the AIGW-managed client request.

#### Scenario: A caller uses an unknown namespace

- **WHEN** a request path does not match a control endpoint, one of the three
  canonical namespaces, or the bounded DMX migration route
- **THEN** the proxy rejects it locally
- **AND** it performs no remote network request.

### Requirement: Provider-specific recovery is route-scoped

The exact DMXAPI HTTP 477 `empty_response` recovery and cooldown SHALL apply
only to the DMXAPI route. A failure or cooldown key from DMXAPI SHALL NOT block,
rewrite, or classify a UCloud/Azure or AIHubMix request. Generic transient and
schema recovery MAY remain shared only where its trigger is provider-neutral
and exact.

#### Scenario: DMXAPI enters empty-response cooldown

- **WHEN** a DMXAPI request exhausts its exact HTTP 477 recovery and the same
  portable body is then sent to UCloud/Azure or AIHubMix
- **THEN** the other provider request is attempted normally
- **AND** no DMXAPI cooldown response is reused across the route boundary.

#### Scenario: A non-DMX provider returns HTTP 477

- **WHEN** UCloud/Azure or AIHubMix returns HTTP 477
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

### Requirement: Conversation state remains owned by Codex

The compatibility path SHALL NOT edit Codex JSONL, SQLite, transcript history,
archived conversations, hidden resume pointers, or per-conversation model
metadata. Success SHALL require an unchanged original conversation to complete
multiple turns after the provider sequence DMXAPI, UCloud/Azure, AIHubMix, and
DMXAPI again.

#### Scenario: The integrated fix is accepted

- **WHEN** the released proxy and AIGW projections are installed and the same
  original conversation completes at least two turns on each leg of
  DMXAPI to UCloud/Azure to AIHubMix to DMXAPI
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
