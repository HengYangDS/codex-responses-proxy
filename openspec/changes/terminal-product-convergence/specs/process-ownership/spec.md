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

#### Scenario: A macOS launch-agent carrier is unowned or indirect

- **WHEN** its home-relative path has a symbolic-link ancestor or leaf, the leaf
  is not a regular file, or its label, watchdog arguments, user home or executable
  ownership disagree with this installation
- **THEN** installation and teardown reject the carrier before service mutation
- **AND** preserve the carrier and all unrelated target bytes
- **AND** current source reuses the existing safe owned-file I/O boundary.

#### Scenario: A verified macOS carrier is replaced or removed

- **WHEN** native replacement has proved predecessor process and registration
  removal and the accepted successor carrier must be persisted
- **THEN** its write is atomic and does not follow symbolic links
- **AND** teardown rechecks the exact verified carrier bytes before unlinking
- **AND** a changed or substituted carrier is preserved with a lifecycle error.
