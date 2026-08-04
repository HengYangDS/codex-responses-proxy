## ADDED Requirements

### Requirement: Repository-owned verification separates wheel compatibility from native distribution

Python compatibility and quality sessions SHALL build and install the project
wheel, then exercise the complete behavior inventory through that installed
environment. They MUST NOT rebuild the native distribution. The release session
SHALL be the sole native executable build owner and SHALL prove CLI behavior,
real handoff behavior, no-Python execution, and release-asset packaging.

#### Scenario: Python and native gates prove distinct facts

- **WHEN** repository verification runs the supported Python matrix and release gate
- **THEN** each Python version proves the installed wheel and console executable
- **AND** exactly one release session builds and black-box tests the native executable
- **AND** both surfaces retain their complete owned behavior tests.
