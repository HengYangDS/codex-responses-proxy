# Verification diagnostics delta

## ADDED Requirements

### Requirement: Supply-chain pins are current and reproducible

Project metadata SHALL declare exact audited stable quality and packaging
dependencies, the committed uv lock SHALL own their transitive closure, and
hosted Actions SHALL use immutable revisions of audited stable releases.

#### Scenario: The supply chain advances

- **WHEN** an audited stable dependency or hosted Action release supersedes the
  repository pin
- **THEN** its existing SSOT is updated without adding a parallel version owner
- **AND** lock, workflow, and repository quality contracts pass together.
