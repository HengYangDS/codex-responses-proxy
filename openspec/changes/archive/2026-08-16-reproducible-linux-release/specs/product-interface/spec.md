## MODIFIED Requirements

### Requirement: Repository-owned verification separates wheel compatibility from native distribution

Python compatibility and quality sessions SHALL build and install the project
wheel, then exercise the complete behavior inventory through that installed
environment. They MUST NOT rebuild the native distribution. The release session
SHALL be the sole native bundle build owner and SHALL prove CLI behavior, real
handoff behavior, no-Python execution, prewarmed startup, and release-asset
packaging. Release validation SHALL exercise the exact native executable that
installation will serve. A temporary copy SHALL NOT be treated as proof that
the final installed inode has paid its first-start cost.

#### Scenario: Python and native gates prove distinct facts

- **WHEN** repository verification runs the supported Python matrix and release
  gate
- **THEN** each Python version proves the installed wheel and console executable
- **AND** exactly one release session builds and black-box tests the native
  bundle
- **AND** the release test prewarms and starts the exact installed executable
  within the configured installation deadline
- **AND** both surfaces retain their complete owned behavior tests.

#### Scenario: An operator upgrades a running installation

- **WHEN** a verified release is committed as the successor projection
- **THEN** the exact installed executable completes a bounded prewarm probe
- **AND** the handoff uses the operator's configured installation deadline.
