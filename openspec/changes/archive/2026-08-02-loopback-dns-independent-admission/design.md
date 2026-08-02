## Context

The inherited HTTP server bind path resolves a hostname only to populate
presentation attributes. On a hosted macOS runner that lookup stalled before
`listen()`, so every listener test reached its timeout even though socket
binding itself was valid. The product accepts only loopback traffic and already
possesses the authoritative kernel-bound address.

## Decisions

### Admission uses the transport primitive directly

Listener construction uses the TCP server bind operation rather than the HTTP
server presentation wrapper. It then sets the public listener name and port
from the resulting bound address. No alternate hostname fallback exists.

### Fresh and adopted listeners share one identity rule

A fresh listener and a protocol-v2 handoff listener both derive their displayed
identity from `getsockname()` or the equivalent bound address. Handoff does not
re-resolve a host name and therefore cannot reintroduce the startup dependency.

### The regression test fails closed on DNS access

The contract makes hostname resolution raise while constructing both listener
forms. Successful construction plus exact bound-address assertions prove that
admission did not consult DNS and did not fabricate an identity.

## Boundaries

This change does not alter loopback enforcement, socket ownership, handoff
authorization, request concurrency, provider cooldown, retry behavior, or
supervision. It adds no compatibility facade or new runtime entity.

## Rollback

Before publication, revert the atomic listener change and this record together.
After publication, ship a new signed release; do not edit an installed payload
or published Git history in place.
