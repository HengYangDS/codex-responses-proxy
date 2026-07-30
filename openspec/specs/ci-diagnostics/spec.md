# CI diagnostics

## Purpose

Codex DMX Proxy SHALL require successful CI jobs to be free of unhandled Python
tracebacks and warnings.
## Requirements
### Requirement: Capability boundary

The CI diagnostics capability SHALL own diagnostic cleanliness across the
repository test runner, quality gate, dependency bootstrap, and provider
projections without owning application logs or provider infrastructure.
Release-contract tests SHALL verify repository-owner behavior and stable policy
values without depending on private shell syntax.

#### Scenario: A diagnostic contract changes

- **WHEN** a change alters warning, traceback, compile, cache, dependency
  bootstrap, or versioned-tool selection handling
- **THEN** the repository-owned command remains the semantic owner
- **AND** GitLab and GitHub remain thin projections over that command
- **AND** contract tests prove behavior rather than obsolete implementation text.

### Requirement: Passing test jobs have clean diagnostic output

The canonical Python test runner SHALL fail when a test returns nonzero or
emits an unhandled traceback, a `socketserver` exception banner, or a Python
warning. It SHALL use the same compile-and-test entrypoint across supported
interpreters and Forge operating systems.

#### Scenario: A passing test leaks a warning

- **WHEN** a test process exits successfully but emits a Python warning
- **THEN** the canonical runner rejects the test job
- **AND** the hosted provider cannot report that revision as verified.

### Requirement: Expected disconnects and HTTP errors retain one owner

Production handoff control SHALL close failed HTTP responses. Loopback test
fixtures MAY suppress only peer-disconnect errors caused intentionally by the
test; unrelated server exceptions SHALL remain visible.

#### Scenario: A loopback client disconnects before the upstream writes

- **WHEN** an integration test intentionally closes its client connection
- **THEN** the fixture suppresses only the resulting peer-disconnect error
- **AND** any other request-handler exception remains a failing diagnostic.

### Requirement: Quality tooling leaves no checkout cache

Compilation SHALL write bytecode below an isolated temporary prefix, and Ruff
SHALL run without a persistent checkout cache. Containerized dependency
installation SHALL explicitly select its noninteractive policy, suppress
routine package-manager chatter, and emit neither root-user nor frontend
fallback warnings.

#### Scenario: A clean quality gate completes

- **WHEN** the repository-owned quality command succeeds
- **THEN** no bytecode, coverage file, or Ruff cache remains in the checkout
- **AND** the job log contains no pip root-user or Debian frontend warning.
