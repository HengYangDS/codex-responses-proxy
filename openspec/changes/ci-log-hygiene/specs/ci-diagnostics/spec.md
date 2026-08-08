# CI diagnostics delta

## ADDED Requirements

### Requirement: Hosted setup is deterministic and contention-free

GitHub workflows SHALL initialize Git explicitly, and concurrent Python matrix
jobs SHALL use distinct `setup-uv` cache identities.

#### Scenario: Hosted verification runs concurrently

- **WHEN** supported Python versions execute in parallel
- **THEN** each macOS matrix job uses its interpreter as the cache suffix
- **AND** Git resolves `main` without an initialization hint
- **AND** no verification, release, or provenance gate is weakened
