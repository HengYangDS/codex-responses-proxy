## MODIFIED Requirements

### Requirement: Native handoff completion is portable and generation-bound

Native reload, upgrade, and rollback SHALL admit exactly one verified current
product listener before mutation. The controller SHALL capture that predecessor
process generation and the successor generation named by the protocol. Success
SHALL require the predecessor generation to have exited, the successor
generation to remain alive, and loopback runtime identity to match the exact
finalized transaction. TCP owner attribution after socket transfer SHALL remain
diagnostic rather than authoritative.

#### Scenario: Finalized successor completes a handoff

- **WHEN** the exact successor generation reports accepting finalized identity
  for the requested transaction
- **AND** the exact predecessor generation has exited
- **THEN** the lifecycle command reports success with the successor PID.

#### Scenario: Shared socket ownership remains attributed to the predecessor

- **WHEN** the operating system still attributes the transferred socket to the
  predecessor PID
- **AND** the captured predecessor generation has exited and the captured
  successor generation serves exact finalized identity
- **THEN** the lifecycle command reports success without waiting on the stale
  TCP-owner projection.

#### Scenario: Predecessor generation remains alive

- **WHEN** finalized successor health is visible but the captured predecessor
  generation remains alive
- **THEN** the lifecycle command does not report success
- **AND** it fails closed if generation convergence does not occur within the
  configured bound.

#### Scenario: Controller failure is resolved

- **WHEN** the controller loses the direct result after requesting handoff
- **THEN** failure resolution reuses the exact captured predecessor generation
  and the same successor-finalization predicate
- **AND** it reports an unknown outcome rather than reconstructing ownership
  from a PID or TCP table alone.

#### Scenario: Published predecessor predates selected-generation handoff

- **WHEN** a verified published predecessor advertises protocol-v2 handoff but
  does not declare `selected-generation-handoff`
- **THEN** deployment does not ask that predecessor to launch a payload outside
  its executable root
- **AND** uses the bounded native process-generation replacement after the
  candidate and supervisor projection are committed.

#### Scenario: Native replacement falls back to its predecessor

- **WHEN** the predecessor has closed Responses admission and successor proof
  fails before a successor becomes authoritative
- **THEN** deployment restores predecessor supervision
- **AND** reopens admission only through the exact still-owned predecessor
- **AND** reports an unknown recoverable outcome if reopening cannot be proved.

#### Scenario: Runtime and lifecycle read one selector authority

- **WHEN** either the running service or lifecycle controller resolves the
  immutable payload selector
- **THEN** both enforce the same canonical schema, exact field set, generation
  names, and selected payload identity
- **AND** neither accepts a selector that the other rejects.
