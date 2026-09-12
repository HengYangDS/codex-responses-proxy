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

- **WHEN** image-capable input contains a nonempty, strictly Base64-encoded
  PNG, JPEG, WebP, or GIF data URL
- **THEN** projection retains its original URL, detail, and order in dialogue
  and paired tool-output input, including image-only content
- **AND** repeated projection and classified retries preserve the image bytes
- **AND** validation performs no filesystem access, network fetch, raster
  decoding, or image re-encoding.

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
