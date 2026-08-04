## ADDED Requirements

### Requirement: The default local queue wait covers one upstream stream deadline

The default bounded local queue wait SHALL NOT be shorter than the default total
upstream stream deadline that bounds the route-slot holder it waits on. A
waiting request SHALL NOT be denied while the holder ahead of it is still inside
its own deadline. The operator override and its validated bounds SHALL remain
unchanged, and per-route admission SHALL remain single-flight.

#### Scenario: A waiter queues behind a legitimate long turn

- **WHEN** a request waits on a provider route whose current holder is still
  streaming inside the total upstream deadline
- **THEN** the waiting request is not denied for exhausting its queue wait
- **AND** it is admitted once the holder releases the route slot.

#### Scenario: The upstream deadline is retuned

- **WHEN** the default total upstream stream deadline changes
- **THEN** the default local queue wait covers the new deadline without a
  separate edit.
