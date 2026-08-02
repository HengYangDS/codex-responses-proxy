## MODIFIED Requirements

### Requirement: Native platform parsers retain host-independent contracts

A platform-native process parser SHALL have deterministic synthetic contracts
for its wire representation and platform-derived defaults on every supported
test host. Those contracts SHALL cover valid decoding and malformed native
payload rejection without loading or calling a foreign operating-system
symbol. A real operating-system integration MAY remain restricted to the
platform that implements the native system call.

#### Scenario: Linux verifies Darwin argv decoding

- **WHEN** a Linux quality job executes the supported product suite
- **THEN** synthetic valid and incomplete `kern.procargs2` payloads exercise
  successful decoding and fail-closed rejection without loading or calling
  Linux `libc.sysctl`
- **AND** the real child-process integration remains Darwin-only
- **AND** branch coverage stays strictly above the repository floor.

#### Scenario: Every host verifies Darwin default paths

- **WHEN** a supported test host evaluates platform-derived state and log roots
- **THEN** the Darwin defaults are verified through injected platform identity
- **AND** the test does not depend on the host that runs the suite.
