## ADDED Requirements

### Requirement: Hosted verification bootstrap is bounded and repository-owned

GitLab verification MUST start from an immutable image containing the
repository-selected UV and Python runtime. It MUST reuse the runner cache for
locked package artifacts and MUST NOT reinstall UV or download the job's
primary Python runtime before repository verification. `uv.lock` remains the
sole authority for project and quality dependencies.

#### Scenario: A fresh GitLab job starts verification

- **WHEN** an admitted GitLab runner starts a verification job with an empty
  project workspace
- **THEN** the selected digest-pinned image already provides UV and the job's
  primary supported Python runtime
- **AND** the job installs repository dependencies from `uv.lock`
- **AND** it does not bootstrap UV through pip or download that primary Python
  runtime before invoking the repository-owned Nox graph.

#### Scenario: A runner cache is empty or unavailable

- **WHEN** no reusable dependency cache is present
- **THEN** the job remains correct from the immutable image and committed lock
- **AND** cache absence can affect duration but not dependency authority or
  verification semantics.

#### Scenario: The supported Python matrix executes

- **WHEN** GitLab runs all Python compatibility sessions
- **THEN** `.python-versions` remains the only supported-version inventory
- **AND** additional matrix interpreters may be acquired by UV without making
  their patch versions or installation paths a second repository authority.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Hosted verification bootstrap is bounded and repository-owned` | `2.1` | `tests/forge/test_workflow_contracts.py::test_gitlab_verification_bootstrap_is_bounded_and_cached` |
