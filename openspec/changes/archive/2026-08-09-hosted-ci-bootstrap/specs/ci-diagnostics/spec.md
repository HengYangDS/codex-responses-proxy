## MODIFIED Requirements

### Requirement: Hosted product-tool execution uses the locked product environment

Hosted jobs SHALL install the product runtime and locked repository tooling
before executing dependency-bearing repository modules. Repository-only tools
and their tests SHALL run through the selected interpreter's import-safe module
entrypoint.

#### Scenario: Release metadata executes in GitLab

- **WHEN** the GitLab metadata job validates a branch or tag
- **THEN** it installs the complete environment from `uv.lock`
- **AND** the product CLI dependencies are importable.

#### Scenario: Repository quality executes in either Forge

- **WHEN** a hosted job invokes repository quality checks
- **THEN** it uses the package-aware module entrypoint
- **AND** release chronology tests receive complete tag history.

#### Scenario: GitHub resolves the supported Python matrix

- **WHEN** the GitHub verification workflow reads `.python-versions`
- **THEN** it first installs the locked quality environment
- **AND** it invokes the matrix owner through `python -m`
- **AND** no workflow-local parser duplicates the matrix semantics.

#### Scenario: GitLab executes repository release tests

- **WHEN** the GitLab metadata job runs repository-only tests under importlib mode
- **THEN** it invokes pytest through the selected interpreter
- **AND** repository `tools` modules remain importable without `PYTHONPATH`
  injection or a compatibility package.

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `ci-diagnostics:Hosted product-tool execution uses the locked product environment` | `1.2` | `tests/forge/test_workflow_contracts.py::test_github_verification_workflow_contract` |
| `ci-diagnostics:Hosted product-tool execution uses the locked product environment` | `1.3` | `tests/forge/test_workflow_contracts.py::test_gitlab_pytest_invocations_preserve_repository_module_resolution` |
| `ci-diagnostics:Hosted product-tool execution uses the locked product environment` | `1.4` | `tests/quality/test_contract.py::TestVerificationContracts::test_pytest_is_the_only_behavior_test_runner` |
