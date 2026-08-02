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
