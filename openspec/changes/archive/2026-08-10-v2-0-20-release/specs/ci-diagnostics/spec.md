## ADDED Requirements

### Requirement: A patch release has one source identity and independent Forge projections

A patch release MUST derive its package, Changelog, documentation, signed tag,
and assets from one accepted source commit. GitLab and GitHub MUST each complete
their own signed publication without querying, mutating, or depending on the
other Forge.

#### Scenario: Both Forge planes publish the release

- **WHEN** v2.0.20 local exact-HEAD proof passes
- **THEN** GitLab and GitHub each publish a signed `v2.0.20` tag and complete
  native asset set from that same source commit
- **AND** a read-only audit proves source and asset consistency after both
  publications complete

#### Scenario: One Forge publication fails

- **WHEN** either Forge cannot publish v2.0.20
- **THEN** the other Forge remains independently publishable and usable
- **AND** no existing tag, run, Release, or asset is rewritten to hide failure

#### Scenario: A release asset is installed

- **WHEN** an operator installs a v2.0.20 platform archive
- **THEN** the installer verifies the complete release set and external trust
  anchor before mutation
- **AND** the installed executable reports v2.0.20 and passes runtime acceptance.
