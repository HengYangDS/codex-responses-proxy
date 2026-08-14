## MODIFIED Requirements

### Requirement: Hosted Python verification uses the repository toolchain

GitLab SHALL execute supported Python jobs from UV images whose UV version
matches the exact version declared by project metadata. The image reference
SHALL retain an immutable registry digest, and repository Python tools SHALL
use the job's synchronized interpreter without downloading an implicit
replacement.

#### Scenario: GitLab starts a Python verification job

- **WHEN** the floor or latest supported Python image is selected
- **THEN** the image tag contains the UV version declared by `pyproject.toml`
- **AND** the image digest and Python boundary are validated by repository tests
- **AND** UV uses the repository-local Python install and cache directories.

#### Scenario: The image contains an unexpected UV executable

- **WHEN** the observed UV version differs from the project requirement
- **THEN** the job fails before dependency synchronization
- **AND** the diagnostic states both the expected and observed versions.

#### Scenario: A GitLab job runs a Python repository tool

- **WHEN** verification or publication invokes Nox, pytest, or a repository module
- **THEN** UV selects the Python executable synchronized for that job
- **AND** no ambient interpreter or implicit Python download contributes to success.
