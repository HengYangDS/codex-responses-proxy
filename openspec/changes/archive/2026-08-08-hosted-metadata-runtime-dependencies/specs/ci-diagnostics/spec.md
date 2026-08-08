# CI diagnostics delta

## ADDED Requirements

### Requirement: Hosted product-tool execution uses the locked product environment

Hosted jobs SHALL install the product runtime whenever they execute repository
product tools, and SHALL run package-aware tools through import-safe module
entrypoints.

#### Scenario: Release metadata executes in GitLab

- **WHEN** the GitLab metadata job validates a branch or tag
- **THEN** it installs the complete environment from `uv.lock`
- **AND** the product CLI dependencies are importable

#### Scenario: Repository quality executes in either Forge

- **WHEN** a hosted job invokes repository quality checks
- **THEN** it uses the package-aware module entrypoint
- **AND** release chronology tests receive complete tag history
