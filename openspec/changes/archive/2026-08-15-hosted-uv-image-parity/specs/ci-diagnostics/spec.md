## MODIFIED Requirements

### Requirement: Supply-chain pins are current and reproducible

Supported runtimes, direct quality and packaging dependencies, hosted
Actions, CI images, and release tools SHALL use current stable releases through
one repository-owned declaration for each ecosystem. The committed uv lock SHALL
own transitive closure, hosted Actions SHALL use immutable revisions, and GitLab
Python images SHALL bind both the supported Python minor and the exact UV
version declared by project metadata to immutable registry digests. CI SHALL
consume those authorities rather than duplicate version literals or retain
obsolete compatibility fallbacks.

#### Scenario: A GitLab Python image is selected

- **WHEN** a GitLab job selects the supported floor or latest Python image
- **THEN** the reference contains the project UV version, supported Python minor, and a SHA-256 digest
- **AND** both versions match their repository-owned declarations
- **AND** tests derive these relations instead of duplicating the concrete pins.

#### Scenario: The selected image contains an unexpected UV executable

- **WHEN** the observed UV version differs from the project requirement
- **THEN** the job fails before dependency synchronization
- **AND** the diagnostic states both the expected and observed versions.

#### Scenario: A GitLab job runs a Python repository tool

- **WHEN** verification or publication invokes Nox, pytest, or a repository module
- **THEN** UV selects the Python executable synchronized for that job
- **AND** the repository-local Python install and cache directories remain in use
- **AND** no ambient interpreter or implicit Python download contributes to success.

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

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Supply-chain pins are current and reproducible` | `1.1` | `tests/forge/test_workflow_contracts.py; tests/quality/test_verification.py; uv run --locked --no-sync nox -s quick; ethos prove --execute` |
