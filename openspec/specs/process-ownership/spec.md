# process-ownership Specification

## Purpose
TBD - created by archiving change windows-successor-ownership. Update Purpose after archive.
## Requirements
### Requirement: protocol-proven successor capture

After handoff health proves the successor PID, transaction, release, payload,
receipt, manifest, serving state, and admission state, cleanup SHALL capture the
same PID generation without depending on a second command-line projection.

#### Scenario: Windows launcher projection differs

- **Given** exact successor health has proved a positive PID
- **And** the native process command line is inaccessible or projected through a launcher
- **When** cleanup captures the successor generation
- **Then** it records the PID and creation time
- **And** termination signals only that exact generation
- **And** temporary payload deletion occurs after confirmed exit

#### Scenario: PID has been reused

- **Given** a captured PID and creation time
- **When** the current process creation time differs
- **Then** cleanup does not signal the process

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
