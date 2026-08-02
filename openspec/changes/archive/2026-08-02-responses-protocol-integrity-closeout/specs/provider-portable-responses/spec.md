# Provider-portable Responses delta

## ADDED Requirements

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

The provider manifest MAY select one optional narrow wire-policy module. Core
transport SHALL depend only on that policy contract and SHALL NOT branch on a
provider name. A provider with no wire difference SHALL require only a manifest
entry.

#### Scenario: A new ordinary provider is added

- **WHEN** its Responses wire behavior matches the provider-neutral core
- **THEN** setup requires only its declarative manifest record
- **AND** no transport, replay, or registry provider-name branch is added.

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
SHALL use a five-second fallback. The
default Responses concurrency SHALL be 8 and configurable through the validated
runtime owner without claiming an undocumented provider quota.

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
