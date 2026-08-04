## ADDED Requirements

### Requirement: Forge fingerprint oracle canonicalizes exact UTC spelling

The independent Git-command oracle SHALL treat strict-ISO `Z` and `+00:00`
date lines as the same exact UTC instant while preserving every other
identity-neutral fingerprint byte.

#### Scenario: Hosted Git renders zero offset explicitly

- **WHEN** a supported hosted Git version emits an author or committer date
  ending in `+00:00`
- **THEN** the oracle canonicalizes only that complete zero-offset date line to
  `Z`
- **AND** tree, message, parent, nonzero offset, and ordering bytes remain
  unchanged.
