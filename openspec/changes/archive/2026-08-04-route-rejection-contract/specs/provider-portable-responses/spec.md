## ADDED Requirements

### Requirement: A local response that precedes its request body ends the connection

A local response emitted before the request body is consumed SHALL declare the
connection closed, so the listener never parses an unread body remainder as the
next request on a persistent connection. The listener SHALL NOT read a request
body it has already refused, and a response emitted after the body is consumed
SHALL keep the connection available for reuse.

#### Scenario: A rejected request carries a body on a persistent connection

- **WHEN** a closed-route or unsupported-method request carries a body and the
  client intends to reuse the connection
- **THEN** the rejection declares the connection closed
- **AND** exactly one response is produced, with no second response derived from
  the unread body.

#### Scenario: An accepted request keeps the connection reusable

- **WHEN** a request whose body the listener consumes is answered locally
- **THEN** the connection remains available for the client's next request.

### Requirement: Responses request projection is fail-closed at the HTTP boundary

Every POST Responses request SHALL pass through fail-closed request projection,
including a zero-length body. This requirement SHALL NOT restate which
provider-scoped paths resolve, which is owned solely by the provider route
requirement.

#### Scenario: A caller sends an empty Responses request

- **WHEN** a POST Responses request has no body
- **THEN** the proxy rejects it locally as invalid JSON
- **AND** no configured provider receives the request.

## MODIFIED Requirements

### Requirement: Provider routes admit only exact Responses and model-catalog targets

The listener SHALL expose provider-scoped loopback Responses targets and exact
read-only model-catalog targets for `dmxapi`, `ucloud`, and `aihubmix`. Each
namespace SHALL resolve only exact, lexically normalized
`POST /<provider>/v1/responses` targets with an optional query to its
release-owned HTTPS upstream mapping, or exact, lexically normalized
`GET /<provider>/v1/models` targets with an optional query to that same mapping.
Responses targets SHALL retain their existing compatibility projection, route-local
admission behavior, queue-timeout retry semantics, and total stream-deadline
behavior. Model-catalog targets SHALL relay once without request-body or response
projection, Responses admission, cooldown, retry, or provider-policy recovery.
Encoded path material, dot segments, duplicate separators, lookalike suffixes,
fragments, absolute targets, unsupported methods, and unrelated endpoints SHALL
be rejected locally. A downstream request SHALL NOT supply or override an upstream
URL or host.

#### Scenario: AIGW selects each governed provider

- **WHEN** AIGW sends otherwise equivalent Requests traffic to
  `/dmxapi/v1/responses`, `/ucloud/v1/responses`, or `/aihubmix/v1/responses`
- **THEN** the proxy sends it only to the matching DMXAPI, UCloud/Azure, or
  AIHubMix HTTPS upstream
- **AND** credentials continue to come from the AIGW-managed client request.

#### Scenario: A client discovers a selected provider catalog

- **WHEN** a client sends `GET /dmxapi/v1/models`, `/ucloud/v1/models`, or
  `/aihubmix/v1/models`
- **THEN** the proxy makes one request only to the matching release-owned
  upstream `/v1/models` path
- **AND** it relays authentication, upstream status, eligible headers, and body
  without Responses replay transformation or recovery.

#### Scenario: A Responses route is locally saturated

- **WHEN** the route-local Responses admission wait expires
- **THEN** the proxy reports the selected provider route, both effective limits,
  and `Retry-After: 5`
- **AND** a catalog request does not consume or wait for a Responses slot.

#### Scenario: A caller uses an unknown namespace

- **WHEN** a request path does not match a control endpoint, one of the three
  canonical Responses targets, one of the three canonical model-catalog targets,
  or the bounded DMX migration route
- **THEN** the proxy rejects it locally
- **AND** it performs no remote network request.

#### Scenario: A caller sends an ambiguous route suffix

- **WHEN** the route contains dot segments, encoded path material, duplicate
  separators, a lookalike suffix, or a method the matched target does not admit
- **THEN** the proxy rejects it locally
- **AND** it does not construct or contact an upstream URL.

## REMOVED Requirements

### Requirement: Responses admission is closed at the HTTP boundary

**Reason**: The requirement carried two rules — which provider-scoped paths
resolve, and how a Responses request body is projected. The routing half
duplicated the provider route requirement and had gone stale against it: it
still claimed that only `/v1/responses` targets resolve, and its
ambiguous-suffix scenario still rejected "a non-Responses endpoint", both
falsified by the admitted read-only `GET /<provider>/v1/models` route. Routing
now has a single owner, the provider route requirement, which also carries the
ambiguous-suffix scenario with the stale clause replaced by the method the
matched target does not admit.

**Migration**: The projection half is restated verbatim, with its empty-body
scenario, under `Responses request projection is fail-closed at the HTTP
boundary`, a name that claims only projection. No behavior is removed; the
implementation is unchanged by this requirement split.
