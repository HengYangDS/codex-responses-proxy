## Why

`route-scoped-backpressure` introduced per-route single-flight admission on
2026-08-03 for one measured reason: the UCloud upstream was returning HTTP 429,
and serializing a route was the cheapest way to stop the proxy from amplifying
its own rate limiting. That reason no longer holds — the upstream no longer rate
-limits — and the mechanism it justified is now pure cost.

The cost was measured on the live listener rather than inferred. Every
`responses_slot_acquired` line for the dmxapi route reports `active=1/8`: the
process-wide bound was never the binding one. Individual holds ran 23 to 69
seconds, and request 38 waited 115 seconds between `request_sanitized` and
`responses_slot_acquired` behind holders that were each healthy. Nothing was
denied — `responses_local_queue_timeouts` stayed at 0 across the window, because
`queue-timeout-invariant` had already widened the wait to one upstream deadline
— so the serialization is invisible to every counter and visible only as
latency. It is what makes a client with its own deadline, such as
`aigw verify --for all`, report `context deadline exceeded` against a proxy that
is behaving exactly as specified.

`RESPONSES_MAX_PER_ROUTE` is also the only admission bound in the product that
is a source constant rather than a validated setting. Every other one — the
process-wide limit, the queue wait, both upstream deadlines — is loaded from the
environment and rendered into the supervised unit. That asymmetry is what makes
the width unsafe to simply raise: if the upstream ever rate-limits again, an
operator would need a new release to serialize a route.

## What Changes

- Source the per-route admission width from validated runtime settings, with the
  operator variable `CODEX_RESPONSES_PROXY_RESPONSES_MAX_PER_ROUTE` and the same
  `1..4096` bounds the process-wide limit already carries.
- Render that setting into the supervised unit, so restoring single-flight is an
  operator act rather than a release.
- Derive its default from the process-wide limit: one provider route may hold at
  most half of process capacity.
- Assert the resulting relationship in the admission unit contract, and restate
  the two requirements that pinned per-route admission at one.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=per-route admission width;
  reuse=extend; change=modify; the per-route width becomes a validated operator
  setting whose default is derived from process capacity instead of a source
  constant fixed at one; facet:lifecycle=admission;
  facet:surface=source,test,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- The process-wide limit `DEFAULT_RESPONSES_MAX_CONCURRENCY`, which this change
  reads but does not retune.
- The local queue wait and its `0.001..3600` bounds, unchanged.
- The total upstream stream deadline, unchanged.
- The provider cooldown mechanism itself. Widening the route bounds how many
  same-route requests can reach a newly rate-limiting provider before the first
  failure is recorded; that bound is stated here and levered by the new setting,
  but the cooldown is not redesigned.
- A per-provider width, which the provider-manifest discipline forbids: the
  width is one process-wide setting applied to every route alike.
- Adding an install-time flag for the width.
- Live provider acceptance and the AIGW `check` and `catalog` contract.

## Impact

One runtime setting, one unit contract, three test contracts, the diagnosis
table, and release notes are affected. No new dependency, daemon, or persistent
state is added. As with every other unit-rendered setting, a supervised listener
observes the new default only after a reinstall re-renders its unit.
