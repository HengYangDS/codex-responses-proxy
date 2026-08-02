## ADDED Requirements

### Requirement: Exact prior protocol-v2 inventories remain upgradeable

The installer SHALL admit a prior protocol-v2 projection only when its complete
manifest file set, per-file digests, serving aggregate, release receipt,
release, and entrypoint match a supported released inventory. When finalized
install state is present it SHALL match the same release and receipt; its
absence MAY be admitted only for an explicitly modeled exact historical
projection. Files owned only by that verified prior inventory SHALL be
snapshotted, removed during candidate commit, and restored by rollback.

#### Scenario: Exact v2.0.0 projection upgrades

- **WHEN** the installed schema-2 manifest exactly identifies the v2.0.0
  runtime inventory, every owned digest matches, its canonical receipt is bound
  to release v2.0.0, and finalized install state is either absent or matching
- **THEN** the installer admits the projection and includes
  `codex_responses_proxy/replay/event.py` in the rollback-bound retired set
- **AND** candidate commit removes that retired path without touching unknown
  content
- **AND** rollback restores the receipt and original absence or presence of
  finalized install state.

#### Scenario: Similar but unknown schema-2 projection is presented

- **WHEN** a schema-2 manifest adds, removes, or changes any path outside a
  supported exact inventory
- **THEN** installation fails before payload mutation.

### Requirement: Listener port has one configurable default

The runtime SHALL define 8792 once as its default listener port. Installer,
control, uninstall, and environment inputs SHALL remain able to select another
valid TCP port. Production modules SHALL consume the named configuration owner
rather than copy listener-port literals.

#### Scenario: No port override is supplied

- **WHEN** runtime configuration is loaded without a CLI or environment port
- **THEN** the listener port is 8792.

#### Scenario: A valid override is supplied

- **WHEN** an operator supplies another valid port through the supported CLI or
  environment contract
- **THEN** that exact port is projected into native supervision and runtime.
