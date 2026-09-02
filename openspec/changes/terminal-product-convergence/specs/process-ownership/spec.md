## ADDED Requirements

### Requirement: Native resource ownership is exact and symmetric

Creation, observation, transition, and teardown of a native service or process
SHALL consume one exact service identity, executable identity, process
generation, installation root, transaction, and platform carrier. Successful,
failed, timed-out, and interrupted test paths SHALL release every resource they
created and SHALL preserve unrelated and canonical installations.

#### Scenario: A native lifecycle test exits by any path

- **WHEN** the test succeeds, fails an assertion, raises an exception, times out,
  or is interrupted
- **THEN** teardown addresses only the exact test-owned service, process
  generations, transaction, payload, command projection, and platform carrier
- **AND** the native host contains no net test-owned resource growth.

#### Scenario: Ownership cannot be proved

- **WHEN** a service, process, file, or registration matches only a prefix or
  historical convention
- **THEN** cleanup preserves it and reports the missing identity proof
- **AND** no broad prefix deletion or process-name termination is attempted.
