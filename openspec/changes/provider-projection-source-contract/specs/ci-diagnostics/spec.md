## ADDED Requirements

### Requirement: Provider projection separates source and target authority

GitHub provider projection SHALL freeze one explicit canonical source ref from
the clean accepted checkout and SHALL recreate only the remote `main` target
with GitHub-native identity and signatures. It SHALL NOT require or create a
local `main` branch, and its command-scoped runner SHALL preserve a failing
child's exit status without emitting a Python traceback.

#### Scenario: Accepted source is dev

- **WHEN** the clean canonical checkout is attached to `dev` and its current
  `HEAD` is selected for GitHub projection
- **THEN** the isolated projection recreates the same source tree at remote
  GitHub `main`
- **AND** no local branch or provider-native tag is created, moved, or rewritten.

#### Scenario: Projection command rejects its invocation

- **WHEN** a provider projection child returns a nonzero status with its own
  diagnostic
- **THEN** the signing runner exits with that status
- **AND** it does not append `Traceback` or `CalledProcessError` output.
