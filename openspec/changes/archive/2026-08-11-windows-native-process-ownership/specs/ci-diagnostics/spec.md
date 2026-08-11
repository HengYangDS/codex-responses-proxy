## MODIFIED Requirements

### Requirement: Hosted fixtures own deterministic repository and process identities

Hosted verification MUST create Git repositories with an explicit non-product
initial branch. Native handoff fixtures MUST capture every successor process
generation proven through expected health identity and MUST confirm those exact
generations have exited before their executable payload is removed.

#### Scenario: Host Git configuration differs

- **WHEN** a quality fixture creates an isolated repository
- **THEN** its initial branch is independent of the host's Git defaults
- **AND** no product integration ref is created implicitly.

#### Scenario: Captured process later denies argv access

- **WHEN** expected health proves a native successor and captures its PID,
  executable, and creation time
- **AND** a later argv lookup is unavailable during process exit
- **THEN** teardown terminates the captured PID generation without relying on
  that later argv lookup
- **AND** payload deletion starts only after the generation is absent.

#### Scenario: A captured PID is reused

- **WHEN** the current process creation time differs from the captured value
- **THEN** teardown treats the captured generation as absent
- **AND** does not signal the new process.

#### Scenario: Process inventory omits a serving successor

- **WHEN** a native handoff fixture has captured the successor at bound health
- **THEN** teardown still terminates that exact generation
- **AND** inventory remains only a secondary discovery path.
