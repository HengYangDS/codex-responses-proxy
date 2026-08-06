## ADDED Requirements

### Requirement: Native lifecycle inspection is self-contained
The released executable SHALL discover listener and process identity on each
supported operating system without requiring an optional host utility outside
the product dependency graph.

#### Scenario: Linux has no lsof executable
- **WHEN** the native Linux lifecycle verifies the listener bound to its port
- **THEN** it SHALL still discover the exact listener PID
- **AND** it SHALL preserve the existing executable-and-private-role identity proof.
