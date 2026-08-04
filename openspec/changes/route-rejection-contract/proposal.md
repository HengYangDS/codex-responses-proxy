## Why

Two defects share one cause: the rejection path was described in one place and
implemented in another, and neither was reviewed against the other after the
model-catalog route was added.

The specification states the route table twice. `Provider routes admit only
exact Responses and model-catalog targets` admits both `POST
/<provider>/v1/responses` and `GET /<provider>/v1/models`. `Responses admission
is closed at the HTTP boundary` then restated, for all provider-scoped routes,
that only `/v1/responses` targets resolve, and its scenario rejected "a
non-Responses endpoint" — which the admitted catalog target now is. The second
statement was correct when Responses was the only route and was left behind when
the catalog route landed. Strict OpenSpec validation does not detect this,
because it checks structure rather than agreement between requirements.

The implementation has the matching wire defect. `Handler.protocol_version` is
`HTTP/1.1`, so connections are persistent by default. `relay` answers a closed
route or an unsupported method before reading the request body, and
`set_drain` answers without reading one at all. None of those responses declared
the connection closed, so the listener returned to its read loop with the unread
body still in the socket and parsed it as the next request line. Measured on the
wire, one rejected request with a body produced two responses: the intended 404
and a spurious `400 Bad request syntax` synthesized from the caller's own JSON.
A client reusing that connection loses its next request.

## What Changes

- Give routing a single owner in the specification. The route-resolution
  sentence is removed from the admission requirement, which now states only
  fail-closed projection; the ambiguous-suffix scenario moves to the route
  requirement and its stale "non-Responses endpoint" wording is replaced by the
  method the matched target does not admit.
- Add a requirement that a local response emitted before its request body is
  consumed declares the connection closed, and that a response emitted after the
  body is consumed leaves the connection reusable.
- Declare `Connection: close` on closed-route rejections, unsupported-method
  rejections, and the drain toggle.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=local rejection route contract and
  connection framing; reuse=extend; change=modify; routing is stated once
  instead of twice, and a response that precedes its request body now ends the
  connection instead of leaving an unread remainder to be parsed as the next
  request; facet:lifecycle=admission; facet:surface=source,test,openspec,claim,
  evidence; facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- The status code and `Allow` header used for an unsupported method. A rejected
  method still answers 404; changing it to 405 is a downstream-visible contract
  change with its own AIGW acceptance and is not bundled here.
- The `provider_route_rejected` counter, which still aggregates both rejection
  kinds even though the log events distinguish them.
- Draining or bounding an unread request body, which this change deliberately
  does not do.
- Route resolution itself, admission width, the queue wait, and the total
  upstream stream deadline, none of which change.

## Impact

One downstream framing helper, one control writer, and one rejection path are
affected, plus the specification text that describes them. No new dependency,
configuration surface, or persistent state is added. A client that today reuses
a connection after a rejection must open a new one; that client was previously
receiving a corrupted response on that connection, so the observable change is a
repair rather than a restriction.
