# CI diagnostics delta

## MODIFIED Requirements

### Requirement: Passing test jobs have clean diagnostic output

The canonical Python test runner SHALL fail when a test returns nonzero or
emits an unhandled traceback, a `socketserver` exception banner, or a Python
warning. It SHALL use the same compile-and-test entrypoint across supported
interpreters and Forge operating systems. Hosted CI SHALL select each supported
minor release line rather than one platform-specific patch build.

#### Scenario: A passing test leaks a warning

- **WHEN** a test process exits successfully but emits a Python warning
- **THEN** the canonical runner rejects the test job
- **AND** the hosted provider cannot report that revision as verified.

#### Scenario: A supported Python patch is absent from one hosted platform

- **WHEN** an official Forge runner does not publish the same patch build as
  another supported operating system
- **THEN** the job resolves a stable patch from the declared supported minor line
- **AND** verification starts without narrowing the 3.12, 3.13, and 3.14 matrix
- **AND** repository contract tests reject patch-pinned hosted CI configuration.
