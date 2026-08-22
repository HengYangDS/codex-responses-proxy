# DR-0006: Require Semantic Fit Before Framework Adoption

- Status: accepted
- Date: 2026-08-22

## Context

The product currently uses the Python standard-library HTTP server for its
loopback ingress and `urllib` for upstream traffic. Mature frameworks can remove
incidental protocol, timeout, validation, and test infrastructure, but a broad
framework can also add a second lifecycle, configuration surface, dependency
graph, and release burden without replacing the product's difficult behavior.

The difficult boundaries are byte-preserving Responses and SSE relay, inherited
listener transfer during a rolling native handoff, bounded drain and recovery,
and one frozen executable on macOS, Linux, and Windows. OpenAPI generation,
general application routing, browser sessions, and public web deployment are
not product responsibilities.

## Decision

Dependencies are admitted by semantic replacement, not popularity. A candidate
must delete or substantially simplify an owned boundary, preserve the exact
product contracts, work in the frozen native distribution, and reduce total
development, verification, and maintenance cost.

FastAPI is not adopted for the loopback ingress. Its primary value—typed API
modeling, validation, OpenAPI, and application routing—does not replace the
native supervision or listener-handoff boundary. Using it would also introduce
an ASGI server and data-model stack while the product must still own raw stream
framing, drain admission, inherited-socket lifecycle, and exact process
identity.

HTTPX is selected for a separate, bounded upstream-transport migration after
the quality-system convergence is complete. Its synchronous streaming client,
typed response surface, connection pooling, raw-byte iteration, and explicit
connect/read/write/pool timeouts can replace the `urllib` response adapter,
private socket traversal, and repeated connection setup. The migration is not
complete until raw encoded response bytes, provider-scoped recovery, bounded
stream deadlines, proxy-environment behavior, release size, and all three
native platforms are proven.

Framework selection and product migration remain separate commits: the current
quality change establishes the admission proof; the transport change must show
actual deletion and behavior parity rather than merely adding a dependency.

## Consequences

- The inbound server stays small and synchronous while that remains the least
  complex implementation of the inherited-listener contract.
- The next transport atom has an explicit deletion target and cannot retain a
  parallel `urllib` implementation after HTTPX acceptance.
- A framework is not rejected because it is external or accepted because it is
  modern; total owned complexity and product fit decide.
- Dependency versions and hashes remain supply-chain projections of the lock,
  not literals copied into CI or documentation.

## Alternatives Considered

- **FastAPI plus Uvicorn for all HTTP behavior:** rejected because it does not
  own native service installation, rolling listener transfer, or byte-level
  relay semantics and would widen the runtime surface before deleting them.
- **Keep `urllib` indefinitely:** rejected because private transport traversal
  and per-request connection construction are accidental complexity with a
  mature typed replacement.
- **Rewrite the entire service as asynchronous code:** rejected as an
  unbounded migration without evidence that concurrency, rather than upstream
  latency and provider behavior, is the limiting product risk.

## Revisit Trigger

Revisit the inbound decision if an ASGI server proves inherited-socket handoff,
raw stream parity, smaller frozen assets, and less owned lifecycle code. Revisit
the HTTPX decision if its native artifacts fail a supported platform, raw-byte
semantics cannot be preserved, or the migration does not delete the existing
transport-specific complexity.
