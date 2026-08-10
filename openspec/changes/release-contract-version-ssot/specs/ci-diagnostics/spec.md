## MODIFIED Requirements

### Requirement: A patch release has one source identity and independent Forge projections

The exact patch identity MUST come from tracked `VERSION`. Its package,
Changelog, documentation, signed tag, and assets MUST derive from one accepted
source commit. GitLab and GitHub MUST each complete their own signed publication
without querying, mutating, or depending on the other Forge.

#### Scenario: Both Forge planes publish the current patch

- **WHEN** local exact-HEAD proof passes for the value in `VERSION`
- **THEN** GitLab and GitHub each publish the corresponding signed tag and complete native asset set from that same source commit
- **AND** a read-only audit proves source and asset consistency after both publications complete.

#### Scenario: One Forge publication fails

- **WHEN** either Forge cannot publish the current patch
- **THEN** the other Forge remains independently publishable and usable
- **AND** no existing tag, run, Release, or asset is rewritten to hide failure.

#### Scenario: A release asset is installed

- **WHEN** an operator installs the platform archive for the value in `VERSION`
- **THEN** the installer verifies the complete release set and external trust anchor before mutation
- **AND** the installed executable reports that exact version and passes runtime acceptance.
