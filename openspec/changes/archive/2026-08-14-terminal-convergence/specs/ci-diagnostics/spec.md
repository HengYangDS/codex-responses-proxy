## MODIFIED Requirements

### Requirement: Verification has one repository-owned owner

Nox SHALL own the complete formatting, lint, typing, security, dependency,
documentation-link, architecture, test, release, and platform verification graph.
The committed uv lock SHALL own Python tool resolution, and project metadata
SHALL declare the exact current stable uv bootstrap used by local and hosted
verification. Warnings, tracebacks, skipped required platforms, and missing
runners SHALL NOT be represented as success. A pending release heading SHALL
match `VERSION` and the current UTC date before either Forge prepares a release.

#### Scenario: A clean checkout is verified

- **WHEN** a contributor or Forge installs the declared uv bootstrap and runs
  the repository command
- **THEN** the lock supplies every runtime and quality dependency
- **AND** Nox resolves the Python matrix from `.python-versions`
- **AND** no ambient user site, another repository environment, or unpinned
  package resolution contributes to success.

#### Scenario: Release preparation crosses a UTC date boundary

- **WHEN** a pending version has not been tagged and its Changelog date is no longer the current UTC date
- **THEN** release preparation fails closed
- **AND** the heading is advanced before proof, tagging, or publication.

#### Scenario: Provider-native tags are checked

- **WHEN** GitLab or GitHub validates release history
- **THEN** the provider checks its own reachable SemVer tags and corresponding
  Changelog headings
- **AND** tag creation time is not required to equal the Changelog date
- **AND** the two publication planes remain independently verifiable.

#### Scenario: GitLab runs a repository Python tool

- **WHEN** a GitLab job invokes release or quality Python code
- **THEN** it runs through `uv run --locked --no-sync`
- **AND** no ambient interpreter or uninstalled runtime dependency contributes
  to the result.

#### Scenario: GitLab project coordinates contain namespaces

- **WHEN** runner admission queries a project whose coordinate contains `/`
- **THEN** the coordinate is encoded as one GitLab project identifier
- **AND** the runner API request resolves the intended project rather than a
  truncated path.

#### Scenario: The uv bootstrap advances

- **WHEN** the current stable uv patch is available
- **THEN** project metadata and its executable contract name that same exact version
- **AND** the dependency lock and product runtime semantics remain unchanged.

### Requirement: Coverage is strict and host-independent

The complete behavior suite SHALL keep aggregate, statement, branch, and every
semantic package coverage strictly greater than 95 percent. Required platform
branches SHALL be exercised through explicit semantic inputs rather than host
spoofing, exclusions, or CI-only production conditionals.

#### Scenario: A quality gate succeeds

- **WHEN** coverage is reported for the exact candidate tree
- **THEN** every required ratio is greater than 95 percent
- **AND** no required test is skipped merely because the quality host differs
  from the modeled platform.

### Requirement: Supply-chain pins are current and reproducible

Supported runtimes, direct quality and packaging dependencies, hosted
Actions, CI images, and release tools SHALL use current stable releases through
one repository-owned declaration for each ecosystem. The committed uv lock SHALL
own transitive closure, hosted Actions SHALL use immutable revisions, and GitLab
Python images SHALL use supported minor tags bound to immutable registry digests.
CI SHALL consume those authorities rather than duplicate version literals or
retain obsolete compatibility fallbacks.

#### Scenario: A GitLab Python image is selected

- **WHEN** a GitLab job selects the supported floor or latest Python image
- **THEN** the reference contains the supported minor tag and a SHA-256 digest
- **AND** its minor version matches the corresponding boundary in
  `.python-versions`
- **AND** tests derive this relation instead of duplicating the concrete pin.

#### Scenario: The supply chain advances

- **WHEN** an audited stable dependency, hosted Action release, or CI base image
  supersedes the repository pin
- **THEN** its existing SSOT is updated without adding a parallel version owner
- **AND** lock, workflow, and repository quality contracts pass together.

#### Scenario: A stable transitive dependency advances

- **WHEN** the declared uv resolver selects a newer stable transitive dependency
- **THEN** the repository SHALL update only `uv.lock`
- **AND** a repeated resolution SHALL produce no further diff
- **AND** the complete locked verification graph SHALL pass before integration.
