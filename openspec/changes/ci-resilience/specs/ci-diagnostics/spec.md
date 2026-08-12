## ADDED Requirements

### Requirement: Dependency-minimal verification

Hosted verification MUST install only the locked tools required to execute its
declared checks. Native release builders MUST remain in a distinct release
group and MUST be installed only by the native release session.

#### Scenario: Quality verification runs without PyInstaller

- **WHEN** a Python quality or release-metadata job prepares its environment
- **THEN** it installs the `quality` dependency group
- **AND** it does not resolve or install PyInstaller
- **AND** a native release build explicitly installs both `quality` and
  `release`.

### Requirement: Platform-true GitLab evidence

Every GitLab job that represents Linux x86_64 behavior MUST execute an
`linux/amd64` container regardless of the runner host architecture.

#### Scenario: Darwin arm64 runner executes Linux verification

- **WHEN** the registered runner schedules a verification or release job
- **THEN** the selected image declares `linux/amd64`
- **AND** the resulting evidence is not labeled from the runner host
  architecture
- **AND** no GitHub workflow, tag, asset, or availability is required.
