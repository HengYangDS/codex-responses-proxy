## MODIFIED Requirements

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
