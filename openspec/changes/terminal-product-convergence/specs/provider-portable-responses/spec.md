## ADDED Requirements

### Requirement: Responses semantics have one classification and projection authority

Request admission, replay diagnosis, relationship validation, Provider-portable
projection, and recovery classification SHALL consume one authoritative typed
item and relationship model. A recognized item SHALL have exactly one portable,
Provider-local, or rejected disposition; no sanitizer, adapter, diagnostic path,
or fallback SHALL reinterpret it independently.

#### Scenario: One replay enters the request path

- **WHEN** the replay is admitted, diagnosed, projected, retried, or rejected
- **THEN** every stage consumes the same item identities and relationships
- **AND** no duplicate classifier, silent deletion, invented history, or
  unknown-item fall-through changes its meaning.

#### Scenario: Replay contains an inline screenshot

- **WHEN** image-capable input contains an HTTP(S) image URL or a nonempty,
  strictly Base64-encoded PNG, JPEG, WebP, or GIF data URL
- **THEN** the shared content projection preserves the original URL, detail,
  content order, and image-only message or paired tool output
- **AND** repeated projection and classified retries retain those image bytes without increasing
  the omitted-image count
- **AND** transport validation performs no filesystem access, network image
  fetch, raster decoding, or image re-encoding. Local file references and
  malformed image transports retain their existing disposition.

#### Scenario: A running tool delivers later results

- **WHEN** a function or custom-tool call already has its initial result and
  later output items have distinct nonempty item IDs, the same call kind and
  `call_id`, and a nonempty tool name matching the original call
- **THEN** projection keeps the original pair and emits each later result as
  an explicitly attributed `tool_delivery` assistant commentary message at its
  original position, retaining the visible text, call identity and tool name
- **AND** projection, diagnosis and recovery use the same relationship decision;
  a recovery suffix cannot retain a delivery after removing its original call
- **AND** no result replaces an earlier result, no synthetic call is invented,
  and repeated projection is byte-stable. This named textual delivery contract
  does not imply support for every native asynchronous API feature.

### Requirement: Provider extension is adapter-only

A new upstream Provider SHALL be admitted through one manifest entry, one narrow
wire adapter, one policy declaration, and the common conformance suite. Generic
HTTP admission, Responses semantics, lifecycle, CLI, and client configuration
SHALL NOT branch on Provider names.

#### Scenario: A Provider is added

- **WHEN** its endpoint and wire differences are declared
- **THEN** the common conformance suite proves request, stream, non-stream,
  error, retry, cooldown, and redaction behavior
- **AND** no existing generic product module requires Provider-specific code.

### Requirement: HTTP event-stream commitment and release are irreversible

Each HTTP Responses stream SHALL forward validated available events without
waiting to fill an application buffer or for upstream EOF. A terminal
`response.completed`, `response.incomplete`, or `response.failed` event SHALL
finish that response's stream; subsequent bytes SHALL NOT reopen or extend it.
This single-response HTTP contract SHALL NOT be applied to a persistent
WebSocket that can carry successive responses and steering events.

Every upstream attempt SHALL release its connection after success, rejection,
exception or downstream disconnect. Before downstream commitment, a malformed
event SHALL yield one structured HTTP failure. After commitment, malformed or
unterminated output SHALL close the existing response without a second status
line, a successful chunk terminator, fabricated completion or request replay.
Only the existing classified pre-content recovery may reopen a request.

#### Scenario: A complete event arrives on a held-open chunked connection

- **WHEN** the upstream sends a terminal event but leaves its HTTP connection open
- **THEN** the client receives that complete response without waiting for EOF
- **AND** the upstream attempt is released without another request.

#### Scenario: The client disconnects during a write

- **WHEN** a downstream header or body write raises an exception
- **THEN** the owned upstream response is closed exactly once
- **AND** no retry starts for the disconnected client.

#### Scenario: A malformed event follows visible content

- **WHEN** HTTP 200 and validated content have already reached the client
- **THEN** the client observes a truncated response, not a second HTTP 503
- **AND** the proxy records the failure and releases the upstream connection.

## MODIFIED Requirements

### Requirement: Unproved replay shapes fail closed

Before upstream I/O, the proxy SHALL classify each Responses input item through
one authoritative item policy shared by diagnostics and provider-portable
projection. Malformed JSON, invalid input containers, genuinely unknown replay
item types, unknown content block types, orphaned or mismatched tool outputs,
duplicate call identities, repeated output item identities, unproven repeated
outputs, invalid required fields, and incomplete local shell pairs SHALL be
rejected locally. A later named textual delivery with a distinct item identity
and matching original call SHALL retain its explicit delivery semantics rather
than become a second paired output. The error SHALL identify a bounded
structural reason without returning request text, credentials, or ciphertext.

#### Scenario: A future client introduces an unknown replay item

- **WHEN** the input list contains an item not recognized by the item policy
- **THEN** the proxy returns a local error identified as an unknown item
- **AND** no configured provider receives the request.

#### Scenario: A recognized client item lacks portable semantics

- **WHEN** the policy recognizes an item but has no safe portable projection
- **THEN** the proxy returns a bounded schema-drift error
- **AND** no configured provider receives the request.

#### Scenario: A tool output is not safely paired

- **WHEN** an output precedes its call, names an unknown `call_id`, repeats an
  output item identity, lacks required delivery provenance after the first
  result, or does not match the original call kind and name
- **THEN** the request is rejected without deleting, reordering or inventing
  tool history.

#### Scenario: Codex local shell history is provider-local

- **WHEN** replay contains a `local_shell_call` with a valid closed `exec`
  action, supported status, exactly one matching `function_call_output`, and
  a current dialogue item
- **THEN** the proxy removes the complete local shell pair before upstream I/O
- **AND** it preserves the dialogue; unpaired calls, invalid statuses, unknown
  action fields and invalid action values remain local rejections.

#### Scenario: Diagnostic and projection classification agree

- **WHEN** the proxy diagnoses and projects the same input item
- **THEN** both operations consume the same item and relationship policy.
