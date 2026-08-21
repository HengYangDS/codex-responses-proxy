## MODIFIED Requirements

### Requirement: Handoff finalization observes the exact successor

After commit, the controller SHALL read bounded health snapshots through the
shared listener until the complete expected successor identity is served. A
snapshot from the retiring process, a transient socket failure, or a transient
health read failure SHALL be treated as an observation to retry, not success or
immediate failure. Deadline expiry SHALL identify the failed lifecycle phase
without including exception messages, request content, headers, credentials,
or upstream payloads.

#### Scenario: A health read fails during ownership transfer

- **WHEN** a post-commit health read raises an ordinary exception
- **THEN** the controller continues bounded observation
- **AND** finalizes only after the exact successor PID and payload identity are
  accepting and not draining
- **AND** rolls back if the deadline expires without that proof.

#### Scenario: The retiring listener answers during ownership transfer

- **WHEN** the first post-commit health snapshot still identifies the retiring
  process
- **THEN** the controller continues bounded observation
- **AND** finalizes only after the exact successor PID and payload identity are
  accepting and not draining.

#### Scenario: Successor observation does not converge

- **WHEN** the deadline expires or health observation fails
- **THEN** the transaction follows its rollback or recovery-required contract
- **AND** operational output records only the failed phase and exception class.

#### Scenario: An install-owned alternate launcher is active on a POSIX host

- **WHEN** the current payload identity, sole listener PID, process generation,
  supervisor declaration, and alternate launcher path all agree
- **THEN** installation atomically bridges that launcher to the canonical native
  executable
- **AND** protocol-v2 handoff starts and proves the canonical native listener
- **AND** the supervisor is rebound before the bridge and retained original are
  removed.

#### Scenario: An alternate launcher is presented on Windows

- **WHEN** installation observes a noncanonical launcher on Windows
- **THEN** it rejects that launcher before service or payload mutation
- **AND** the canonical Windows native install, reload, status, doctor, and
  uninstall lifecycle remains unchanged.

#### Scenario: Reconciliation fails before native handoff

- **WHEN** handoff cannot prove the canonical native successor
- **THEN** the exact alternate launcher is restored
- **AND** no candidate payload mutation begins.

#### Scenario: The native listener committed before controller interruption

- **WHEN** a retry observes the canonical native listener and the supervisor
  still declares the exact retained bridge
- **THEN** installation proves the same listener identity, rebinds the
  supervisor, and removes the bridge residue
- **AND** candidate payload mutation begins only after that convergence.
