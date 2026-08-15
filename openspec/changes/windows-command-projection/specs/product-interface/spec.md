## MODIFIED Requirements

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Human output SHALL use
consistent sections, display-width alignment, actionable failure guidance, and
no serialized object dump. Source modules, Python launch syntax, repository
paths, and release-operator commands SHALL remain outside the end-user journey.
Status SHALL report release identity from the verified installed-state record
and command discoverability without consulting repository files or a second
state authority. An installed command path SHALL be interpreted using the
native absolute-path and link semantics of the host that recorded it.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, command, service, and listener
  state in a scannable layout
- **AND** `status --json` exposes the same semantics
- **AND** Windows accepts its recorded native absolute command path without
  treating a foreign path syntax as valid
- **AND** `doctor` classifies a missing or foreign command projection as an
  actionable failure
- **AND** neither output exposes a Python module invocation or source-checkout
  requirement.
