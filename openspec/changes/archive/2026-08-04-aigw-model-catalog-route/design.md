## Context

See `proposal.md` for the incident. The provider registry currently treats only
`/<provider>/v1/responses` as a valid namespace. The listener already directs
GET traffic through the common route owner, but that owner rejects `/models`
before opening an upstream connection. The proxy must remain a data-plane
adapter; AIGW retains catalog policy, credentials, endpoint selection, and
client projection ownership.

## Goals / Non-Goals

**Goals:**

- Extend the registry's closed grammar with one exact `models` resource.
- Relay the catalog via the existing direct upstream transport while preserving
  client authentication and upstream HTTP semantics.
- Keep all Responses-specific transformation and recovery inaccessible from
  model catalog requests.

**Non-Goals:**

- No model filtering, caching, catalog parsing, profile mutation, or AIGW
  configuration access in the proxy.
- No generic arbitrary-method or arbitrary-path forwarding.
- No direct endpoint substitution, listener lifecycle action, or conversation
  record change.

## Decisions

### Registry resolves a closed resource kind

The registry will parse exactly `/<provider>/v1/responses` and
`/<provider>/v1/models`, returning the corresponding release-owned upstream
URL. This makes route admission the sole owner of namespace grammar and avoids
a transport-level provider/path switch.

Alternative: make the proxy pass every `/<provider>/v1/*` route upstream.
Rejected because it turns a compatibility adapter into an unbounded API proxy
and weakens the existing fail-closed boundary.

### Catalog transport uses a separate transparent relay path

The response route owner will dispatch a resolved `models` GET through a
separate single-attempt read-only opener and common transparent body relay. It
does not create a Responses `Exchange`, read a request body, sanitize replay,
acquire Responses admission capacity, or use cooldown/recovery policy. This
preserves exact catalog response status, allowed headers, and body while
keeping all mutations within the existing `/responses` path.

Alternative: reuse `Exchange` with a boolean. Rejected because it couples
non-Responses catalog reads to recovery state and makes future accidental
request rewrites easier.

### Test through the loopback HTTP surface

The shared fixture will gain exact GET capture so tests can verify the upstream
path, propagated authorization, method, raw catalog body, and rejection of
unsupported methods/routes. Registry unit tests will prove grammar closure.

## Risks / Trade-offs

- [A provider has no `/models` endpoint] → Relay its authentic upstream status;
  do not fabricate a catalog or change its account configuration.
- [Catalog body is larger than a Responses result] → Stream it through the
  transparent bounded body relay rather than apply terminal-Response buffering.
- [A new resource is accidentally broadened] → Require exact method/path tests
  for all accepted and rejected forms.

## Migration Plan

1. Land and release the source change through the normal dual-forge process.
2. Install the released payload with the existing transactional installer; it
   retains rollback to the prior payload if listener identity proof fails.
3. Re-run `aigw check` and `aigw catalog`; prove the original DMXAPI
   Responses path still completes independently.
4. If runtime acceptance fails, roll back the released proxy payload through
   its native lifecycle command. AIGW configuration remains unchanged.
