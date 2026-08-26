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
