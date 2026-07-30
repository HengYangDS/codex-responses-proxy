## ADDED Requirements

### Requirement: AIGW route state uses canonical provider-scoped endpoints

The proxy SHALL bind every newly written AIGW route-state record to one explicit
provider route from `dmxapi`, `ucloud`, or `aihubmix`, separately from the AIGW
account identifier. The recorded proxy URL SHALL equal the scoped loopback base
for that route and installed listener port. New AIGW state and transitions SHALL
NOT record or emit the unscoped `/v1` endpoint; that endpoint MAY remain only as
the bounded direct-Codex compatibility and migration route.

#### Scenario: A canonical scoped AIGW route is adopted

- **WHEN** the canonical AIGW account endpoint equals the exact scoped loopback
  base selected by an explicit provider route, or equals the exact recorded
  direct URL
- **THEN** `adopt-aigw` atomically records schema-v3 state with the separate
  account, provider route, scoped proxy URL, and direct URL
- **AND** the proxy does not edit AIGW configuration or infer the provider route
  from the account name.

#### Scenario: Legacy AIGW state is migrated

- **WHEN** a valid schema-v2 AIGW record contains the historical unscoped DMX
  proxy URL and AIGW has already projected the selected account to its canonical
  scoped endpoint
- **THEN** the existing `adopt-aigw` command is the sole proxy-owned migration
  entry that replaces the record with validated schema-v3 state
- **AND** no enable, adoption, or migration transition writes `/v1` back into
  the canonical AIGW endpoint.

#### Scenario: A legacy or unrelated canonical endpoint is not guessed

- **WHEN** the canonical AIGW endpoint is still the unscoped migration URL or is
  neither the exact direct URL nor the selected provider-scoped URL
- **THEN** adoption fails closed and preserves the prior proxy-owned state
- **AND** the operator must use AIGW's public lifecycle for any endpoint change
  before retrying adoption.

#### Scenario: A managed AIGW route is toggled

- **WHEN** validated schema-v3 state authorizes enable or disable
- **THEN** enable delegates the exact scoped proxy URL and disable delegates the
  exact recorded direct URL through AIGW's public CLI
- **AND** canonical AIGW state is re-read and verified before success is
  reported.

#### Scenario: Direct Codex compatibility remains bounded

- **WHEN** an exact managed `codex_config` route uses the historical unscoped
  `/v1` endpoint
- **THEN** its existing hash-bound disable and uninstall restoration remain
  available as the bounded direct-Codex compatibility path
- **AND** that state is never treated as provider-scoped AIGW authority.

#### Scenario: Scoped state uses a non-default listener port

- **WHEN** validated state contains a canonical scoped loopback URL with an
  explicit supported port
- **THEN** installed control discovers the port by parsing the URL structure
- **AND** credentials, another host, an unknown route, query, fragment, or an
  invalid port grants no route authority.
