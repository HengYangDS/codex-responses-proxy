## MODIFIED Requirements

### Requirement: Quality evidence covers the complete product surface

The repository SHALL enforce formatting, linting, typing, security, dependency,
documentation-link, architecture, release, and platform gates. Statement,
branch, and package coverage SHALL each be strictly greater than 95% for the
declared production surface.

#### Scenario: A release candidate is proved

- **WHEN** full local and hosted verification completes
- **THEN** every required gate reports pass for the exact candidate revision
- **AND** no warning, traceback, skipped required platform, or missing runner is represented as success
- **AND** coverage evidence proves all three thresholds independently.

### Requirement: Supply-chain versions have one maintained authority

Supported runtimes and tools SHALL use current stable releases through one lock
or declarative source appropriate to their ecosystem. CI SHALL consume that
authority rather than duplicate versions in workflow scripts.

#### Scenario: A tool version changes

- **WHEN** the stable locked supply chain is refreshed
- **THEN** local development and both Forge pipelines resolve the same declared version
- **AND** obsolete pins and compatibility fallbacks are removed.
