## ADDED Requirements

### Requirement: Local product closure is Forge-free

The repository SHALL support source verification, current-platform native
build, signed-source admission, installation, status, reload, runtime proof,
and uninstall without GitLab or GitHub availability. Forge publication SHALL be
an optional distribution projection, not a prerequisite for local product
closure.

#### Scenario: Both Forges are unavailable

- **WHEN** a clean accepted checkout has no reachable remote
- **THEN** repository-owned commands can build and verify the current-platform product
- **AND** an operator can install and exercise that accepted local artifact
- **AND** no hosted publication fact is falsely claimed.

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Human output SHALL use
consistent sections, display-width alignment, actionable failure guidance, and
no serialized object dump. Source modules, Python launch syntax, repository
paths, and release-operator commands SHALL remain outside the end-user journey.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, service, and listener state in a scannable layout
- **AND** the same observation remains available without semantic drift through `status --json`
- **AND** neither output exposes a Python module invocation or source-checkout requirement.
