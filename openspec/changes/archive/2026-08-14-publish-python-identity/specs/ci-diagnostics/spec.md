## MODIFIED Requirements

### Requirement: Verification has one repository-owned owner

Nox SHALL own the complete formatting, lint, typing, security, dependency,
documentation-link, architecture, test, release, and platform verification
graph. The committed uv lock SHALL own Python tool resolution, and project
metadata SHALL declare the exact current stable uv bootstrap used by local and
hosted verification. Warnings, tracebacks, skipped required platforms, and
missing runners SHALL NOT be represented as success. A pending release heading
SHALL match `VERSION` and the current UTC date before either Forge prepares a
release.

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
- **AND** synchronized and executed Python identities are equal
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

### Requirement: Hosted verification bootstrap is bounded and repository-owned

GitLab verification MUST start from an immutable image containing the
repository-selected UV and Python runtime. It MUST reuse one target-platform
cache for locked package artifacts and UV-managed Python runtimes, and MUST NOT
reinstall UV, download the job's primary Python runtime, or select a different
Python after synchronizing the locked environment. `uv.lock` remains the sole
authority for project and quality dependencies.

#### Scenario: A fresh GitLab job starts verification

- **WHEN** an admitted GitLab runner starts a verification job with an empty
  project workspace
- **THEN** the selected digest-pinned image already provides UV and the job's
  primary supported Python runtime
- **AND** the job installs repository dependencies from `uv.lock`
- **AND** it does not bootstrap UV through pip or download that primary Python
  runtime before invoking the repository-owned Nox graph
- **AND** subsequent no-sync commands use the synchronized Python identity.

#### Scenario: A runner cache is empty or unavailable

- **WHEN** no reusable dependency cache is present
- **THEN** the job remains correct from the immutable image and committed lock
- **AND** cache absence can affect duration but not dependency authority or
  verification semantics.

#### Scenario: The supported Python matrix executes

- **WHEN** GitLab runs all Python compatibility sessions
- **THEN** `.python-versions` remains the only supported-version inventory
- **AND** additional matrix interpreters may be acquired by UV and stored in
  the declared target-platform cache
- **AND** their patch versions and installation paths do not become a second
  repository authority.
