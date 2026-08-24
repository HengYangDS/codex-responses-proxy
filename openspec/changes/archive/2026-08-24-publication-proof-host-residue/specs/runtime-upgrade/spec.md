## ADDED Requirements

### Requirement: macOS lifecycle leaves no new persistent service projections

On macOS, each bounded native lifecycle SHALL leave the product-owned launchd
registration, process, plist, and override sets unchanged after exact service
teardown. Teardown SHALL address one fully qualified service target and SHALL
NOT reset a launchd domain, match a service-name prefix, or change the canonical
service while cleaning an alternate installation. Historical overrides created
by older product generations SHALL be handled only by a separate exact-label
host migration.

#### Scenario: An isolated macOS lifecycle ends

- **WHEN** an alternate-root lifecycle succeeds, fails, times out, or is interrupted
- **THEN** exact-label teardown removes its service registration, owned processes, and plist
- **AND** the product-owned override set has no net growth
- **AND** the pre-existing canonical service projection and listener remain unchanged
- **AND** the host has no net noncanonical service residue from that lifecycle.
