## ADDED Requirements

### Requirement: Native platform parsers retain host-independent contracts

A platform-native process parser SHALL have a deterministic synthetic contract
for its wire representation on every supported test host. A real operating-
system integration MAY remain restricted to the platform that implements the
native system call.

#### Scenario: Linux verifies Darwin argv decoding

- **WHEN** a Linux quality job executes the supported product suite
- **THEN** a synthetic valid `kern.procargs2` payload exercises the successful
  Darwin decoding branch without loading or calling Linux `libc.sysctl`
- **AND** the real child-process integration remains Darwin-only
- **AND** branch coverage stays strictly above the repository floor.
