## ADDED Requirements

### Requirement: Quality execution is repository-owned

Local and hosted verification SHALL resolve lint, type, and test tools from the
committed `uv.lock` environment rather than ambient global packages.

#### Scenario: Clean hosted checkout

- **WHEN** either Forge verifies the release from a clean checkout
- **THEN** it installs the pinned `uv` bootstrap
- **AND** the repository quality command resolves all remaining tools from the
  committed lock.

### Requirement: Private release assets use authenticated reads

GitLab Release asset verification SHALL fetch private project assets through an
authenticated provider API and hash the returned bytes without text
transformation.

#### Scenario: Private GitLab project asset

- **WHEN** anonymous direct download is unavailable but `glab` is authenticated
- **THEN** the verifier reads the asset through `glab api`
- **AND** compares its byte digest with the canonical release artifact.
