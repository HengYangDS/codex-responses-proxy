## ADDED Requirements

### Requirement: A held provider route slot is bounded by a total stream deadline

The proxy SHALL bound one upstream Responses stream by a total wall-clock
deadline derived from the configured upstream timeout, in addition to the
existing per-read idle timeout. That deadline SHALL span every pre-content
reconnect attempt for the same request. Each per-read wait SHALL be clamped to
the remaining deadline so a blocked read cannot outlive it by a full idle
interval. An upstream connection the relay will not read from again SHALL be
released rather than left for garbage collection.

#### Scenario: A committed stream stalls without idling out

- **WHEN** an upstream stream has written downstream and then stops producing
  events until the total deadline passes
- **THEN** the relay stops reading that stream and reports a deadline outcome
  distinct from a per-read timeout
- **AND** the provider route slot is released.

#### Scenario: A pre-content failure occurs after the deadline

- **WHEN** a stream fails before writing downstream and the total deadline has
  already passed
- **THEN** the relay does not reopen the stream
- **AND** no further reconnect attempt is recorded for that request.

#### Scenario: The relay abandons an upstream response

- **WHEN** the relay stops reading an upstream response, whether at the total
  deadline or because a pre-content reconnect replaces it
- **THEN** that upstream connection is closed at that point.

### Requirement: Local queue-timeout denial names the binding limit and is retryable

When a Responses request exhausts its bounded local queue wait, the proxy SHALL
deny it with a message naming the provider route, that route's admission limit,
and the process-wide limit. The denial SHALL advertise a retry hint. Per-route
admission SHALL remain single-flight.

#### Scenario: A request waits out the local queue timeout

- **WHEN** a Responses request cannot acquire its provider route slot within the
  configured local queue timeout
- **THEN** the client receives HTTP 503 naming the provider route, the route
  limit, and the process limit
- **AND** the response advertises a retry hint for the client to retry the turn.

#### Scenario: One route saturates while process capacity remains

- **WHEN** a single Responses exchange occupies one provider route and the
  process-wide limit is greater than one
- **THEN** the denial for a second same-route request attributes saturation to
  that route rather than to the process limit.
