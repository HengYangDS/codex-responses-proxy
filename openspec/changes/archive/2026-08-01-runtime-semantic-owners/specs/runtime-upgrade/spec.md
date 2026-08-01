## ADDED Requirements

### Requirement: Process-local behavior has concrete semantic owners

Admission and drain, telemetry, safe logging, and provider-neutral cooldown
SHALL be owned by separate concrete modules. Production callers SHALL import
the defining owner directly, and the retired mixed runtime state module SHALL
NOT remain as an implementation or compatibility facade.

#### Scenario: The listener handles a Responses request

- **WHEN** the listener admits, logs, records, or cooldown-checks the request
- **THEN** each operation is delegated to its concrete semantic owner
- **AND** no caller imports a mixed runtime state namespace.

### Requirement: Replay metrics are structured data

Replay normalization SHALL return immutable structured metrics with the
projected bytes and bounded rejection state. Telemetry SHALL consume numeric
fields directly and SHALL NOT parse diagnostic strings.

#### Scenario: Provider-bound replay data is removed

- **WHEN** replay removes response ids, reasoning items, encrypted blocks, or
  unreplayable local images
- **THEN** the result reports each aggregate as a typed field
- **AND** operational diagnostics are derived from that result without
  retaining removed content.

### Requirement: Dual-Forge history parity is identity-aware

Provider-native histories SHALL use the configured Forge author email and
trusted signature. Verification SHALL prove source-to-projection tree, message,
date, and parent-topology correspondence without claiming identical commit
object ids across different identities.

#### Scenario: GitHub publishes a GitLab-accepted source commit

- **WHEN** the required GitHub actor differs from the GitLab actor
- **THEN** publication creates or reuses the verified identity projection
- **AND** rejects destructive updates, ambiguous mappings, or tree/topology drift.
