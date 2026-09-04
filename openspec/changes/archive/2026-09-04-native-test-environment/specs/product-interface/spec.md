## MODIFIED Requirements

### Requirement: Repository-owned verification separates wheel compatibility from native distribution

Python compatibility and quality sessions SHALL build and install the project
wheel, then exercise the complete behavior inventory through that installed
environment. They MUST NOT rebuild the native distribution. The release session
SHALL be the sole native bundle build owner and SHALL prove every public
command's help, valid and invalid inputs, human and JSON output, exit status,
real handoff behavior, no-Python execution, prewarmed startup, and release-asset
packaging. Release validation SHALL exercise the exact native executable that
installation will serve, using an isolated installation root, native service
identity, state root, HOME, and listener port. Native subprocess verification
SHALL preserve the host operating-system runtime environment and override only
the isolated paths owned by the test. A temporary copy or the canonical
installed service SHALL NOT be treated as proof of the release candidate.

#### Scenario: Python and native gates prove distinct facts

- **WHEN** repository verification runs the supported Python matrix and release
  gate
- **THEN** each Python version proves the installed wheel and console executable
- **AND** exactly one release session builds and black-box tests the native
  bundle
- **AND** the release test prewarms and starts the exact installed executable
  within the configured installation deadline
- **AND** the complete public command matrix runs without consulting or mutating
  the canonical installation
- **AND** both surfaces retain their complete owned behavior tests.

#### Scenario: Compatibility evidence uses a published predecessor

- **WHEN** release compatibility verification is explicitly supplied one
  published signed predecessor asset and its external trust anchor
- **THEN** it installs and verifies that exact predecessor before deriving an
  isolated route-controlled fixture from the admitted executable bytes
- **AND** proves ordinary and streaming requests survive the forward upgrade
- **AND** never fabricates a predecessor by changing current release metadata.

#### Scenario: An operator upgrades a running installation

- **WHEN** a verified release is committed as the successor projection
- **THEN** the exact installed executable completes a bounded prewarm probe
- **AND** the handoff uses the operator's configured installation deadline.

#### Scenario: Native verification runs on a supported host

- **WHEN** a native executable test starts a child process on macOS, Linux, or
  Windows
- **THEN** the child retains the host variables required by that operating
  system
- **AND** the test overrides only its isolated home, product roots, and command
  search path
- **AND** absence of Python from that command search path remains proven.
