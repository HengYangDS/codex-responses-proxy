## ADDED Requirements

### Requirement: Quality tool identity excludes informational build metadata

The quality owner SHALL require the exact configured tool name and semantic
version while permitting only an optional space-delimited informational suffix.

#### Scenario: Stable tool reports build metadata

- **WHEN** a pinned tool reports its exact name and semantic version followed by build metadata
- **THEN** the quality owner accepts that executable
- **AND** different versions, prefixes, and malformed suffixes remain rejected.
