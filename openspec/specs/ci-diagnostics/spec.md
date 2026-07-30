# CI diagnostics

## Purpose

Codex DMX Proxy SHALL require successful CI jobs to be free of unhandled Python
tracebacks and warnings.

## Requirements

### Requirement: Capability boundary

The CI diagnostics capability SHALL own diagnostic cleanliness across the
repository test runner, quality gate, and provider projections without owning
application logs or provider infrastructure.

#### Scenario: A diagnostic contract changes

- **WHEN** a change alters warning, traceback, compile, or cache handling
- **THEN** the repository-owned command remains the semantic owner
- **AND** GitLab and GitHub remain thin projections over that command.
