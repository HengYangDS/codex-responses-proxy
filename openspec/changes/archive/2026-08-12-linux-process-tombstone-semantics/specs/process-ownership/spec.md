## ADDED Requirements

### Requirement: Exited process tombstones are terminal

An exact owned process generation SHALL be considered live only while it can
still execute. A zombie record retained by a non-reaping POSIX parent SHALL be
treated as exited, while PID-reuse protection remains unchanged.

#### Scenario: Container PID 1 retains an adopted zombie

- **WHEN** termination has moved an exact owned generation to zombie state
- **AND** the process table still contains its PID and creation time
- **THEN** bounded termination reports that generation exited
- **AND** liveness observation does not report an orphan
- **AND** payload cleanup may proceed

#### Scenario: The PID belongs to a different generation

- **WHEN** the current process creation time differs from the captured value
- **THEN** termination does not signal the current process
- **AND** the captured generation is not claimed as successfully terminated
