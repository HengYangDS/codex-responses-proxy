## MODIFIED Requirements

### Requirement: Local queue-timeout denial names the binding limit and is retryable

When a Responses request exhausts its bounded local queue wait, the proxy SHALL
deny it with a message naming the provider route, that route's admission limit,
and the process-wide limit. The denial SHALL advertise a retry hint. The route
limit named in the denial SHALL be the configured per-route admission width.

#### Scenario: A request waits out the local queue timeout

- **WHEN** a Responses request cannot acquire its provider route slot within the
  configured local queue timeout
- **THEN** the client receives HTTP 503 naming the provider route, the route
  limit, and the process limit
- **AND** the response advertises a retry hint for the client to retry the turn.

#### Scenario: One route saturates while process capacity remains

- **WHEN** concurrent Responses exchanges occupy one provider route up to that
  route's admission width, and the process-wide limit is not yet binding
- **THEN** the denial for a further same-route request attributes saturation to
  that route rather than to the process limit.

### Requirement: The default local queue wait covers one upstream stream deadline

The default bounded local queue wait SHALL NOT be shorter than the default total
upstream stream deadline that bounds the route-slot holder it waits on. A
waiting request SHALL NOT be denied while the holder ahead of it is still inside
its own deadline. The operator override and its validated bounds SHALL remain
unchanged, and the per-route admission width SHALL remain a separate bound.

#### Scenario: A waiter queues behind a legitimate long turn

- **WHEN** a request waits on a provider route whose current holder is still
  streaming inside the total upstream deadline
- **THEN** the waiting request is not denied for exhausting its queue wait
- **AND** it is admitted once the holder releases the route slot.

#### Scenario: The upstream deadline is retuned

- **WHEN** the default total upstream stream deadline changes
- **THEN** the default local queue wait covers the new deadline without a
  separate edit.

## ADDED Requirements

### Requirement: Per-route admission width is an operator-settable share of process capacity

The per-route admission width SHALL be a validated runtime setting projected
into the supervised unit, not a source constant. Its default SHALL be derived
from the process-wide limit so that one provider route holds no more than half
of process capacity, leaving a second route at least as much capacity as the
busiest route holds. Setting the width to one SHALL restore strict single-flight
admission without a new release.

#### Scenario: A busy route leaves capacity for another route

- **WHEN** one provider route holds Responses exchanges up to its full admission
  width
- **THEN** a Responses request on a different provider route is still admitted.

#### Scenario: The process-wide limit is retuned

- **WHEN** the default process-wide admission limit changes
- **THEN** the default per-route width follows it without a separate edit.

#### Scenario: An operator restores single-flight admission

- **WHEN** an operator sets the per-route admission width to one in the
  supervised unit's environment and reloads the listener
- **THEN** same-route Responses exchanges are serialized again without a new
  release.
