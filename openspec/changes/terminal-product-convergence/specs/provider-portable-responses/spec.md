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
