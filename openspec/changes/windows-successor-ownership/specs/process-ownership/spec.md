# Process ownership delta

## ADDED Requirements

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
