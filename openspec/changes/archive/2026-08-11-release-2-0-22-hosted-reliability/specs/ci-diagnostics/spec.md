## ADDED Requirements

### Requirement: Hosted fixtures own deterministic repository and process identities

Hosted verification MUST create Git repositories with an explicit non-product
initial branch. Native handoff fixtures MUST retain every successor PID proven
through expected health identity and MUST confirm those exact processes have
exited before their executable payload is removed.

#### Scenario: Host Git configuration differs

- **WHEN** a quality fixture creates an isolated repository
- **THEN** its initial branch is independent of the host's Git defaults
- **AND** no product integration ref is created implicitly.

#### Scenario: Process inventory omits a serving successor

- **WHEN** a native handoff fixture has observed the successor through bound health
- **THEN** teardown revalidates and terminates that exact PID even if inventory omits it
- **AND** payload deletion starts only after the owned process identity is absent.
