## MODIFIED Requirements

### Requirement: Native supervision is self-contained and portable

The released executable SHALL install and inspect its user service through the
native macOS, Linux, or Windows adapter without an ambient Python interpreter,
optional process utility, source path, user identity, or workstation-specific
coordinate. The default installation SHALL retain the public service identity;
every alternate installation root SHALL use a deterministic identity derived
from that root. Signal paths SHALL revalidate exact process identity
immediately before mutation. Native acceptance on each supported operating
system MUST exercise install, status, recovery, and uninstall through that
platform's built artifact; source tests, mocks, and cross-compilation MUST NOT
be reported as equivalent native product evidence.

#### Scenario: A supported host lacks development tools

- **WHEN** the product is installed on a clean supported host
- **THEN** service installation, listener discovery, handoff, status, and
  uninstall remain available from the released executable alone.

#### Scenario: An alternate root is installed for validation

- **WHEN** a signed asset is installed with a non-default product data root
- **THEN** native supervision SHALL use an identity unique to that absolute root
- **AND** installation SHALL not unload, replace, or report the default service
- **AND** uninstall SHALL address only the alternate identity and its listener.

#### Scenario: The default root is upgraded

- **WHEN** the signed installer targets the canonical product data root
- **THEN** it SHALL use the public service identity and current handoff protocol
- **AND** alternate validation identities SHALL remain untouched.

#### Scenario: A supported host accepts a native release

- **WHEN** the platform-built release artifact is installed into an isolated user root
- **THEN** the public status command reports the exact installed release and healthy owned service
- **AND** recovery reports the correct state without mutating healthy absence
- **AND** uninstall removes the exact owned service, processes, projection, payload, and command
- **AND** the host inventory has no net product residue after teardown

#### Scenario: A native lifecycle fails before completion

- **WHEN** installation, handoff, recovery, or an assertion fails on a supported host
- **THEN** bounded teardown uses the exact resolved service and process identities
- **AND** unrelated or canonical installations remain unchanged
- **AND** any unverifiable owned state remains explicit rather than being deleted by prefix

#### Scenario: A platform runner is unavailable

- **WHEN** one hosted platform cannot schedule a native acceptance job
- **THEN** that platform's product evidence remains unavailable
- **AND** successful evidence from another platform is not relabeled as proof for the unavailable platform

### Requirement: Rollback owns only current product files

Rollback SHALL snapshot the complete current owned inventory or its complete
absence. Unknown install content SHALL be preserved and SHALL never become
implicitly owned. Candidate paths that collide with unknown content SHALL block
mutation. When an upgrade fails after projecting candidate bytes, rollback
SHALL restore every retained prior byte and remove every verified candidate
file that was absent from the prior snapshot.

#### Scenario: Current payload upgrade fails

- **WHEN** candidate commit or successor proof fails
- **THEN** every prior owned bundle byte and mode is restored
- **AND** unknown content remains unchanged.

#### Scenario: Candidate adds a new frozen-runtime member

- **WHEN** an upgrade projects a verified candidate-only file below `bin/`
- **AND** handoff fails and rollback runs
- **THEN** the candidate-only file is removed
- **AND** every prior owned byte and mode is restored exactly
- **AND** content outside prior-owned and candidate inventories is unchanged.

#### Scenario: Candidate collides with unknown content

- **WHEN** a candidate path already contains content outside the current owned inventory
- **THEN** the upgrade blocks before payload mutation
- **AND** rollback never claims ownership of that content.

#### Scenario: Retired payload paths leave empty descendants

- **WHEN** an upgrade removes files owned only by the verified predecessor
- **THEN** it also removes empty directories below those retired file parents
- **AND** it preserves every unowned file and symbolic link
- **AND** rollback restores predecessor-owned bytes without recreating
  semantically empty directory residue.
