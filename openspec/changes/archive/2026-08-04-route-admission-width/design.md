## Context

`admission.admit_response` acquires two bounded semaphores in order: the route
semaphore, then the process-wide one. The route semaphore's width has been the
literal `1` since `route-scoped-backpressure`, making it the only admission
bound not sourced from `runtime.config.SETTINGS`. Its original justification was
a rate-limiting upstream, and `route-slot-lease` later declined to widen it
because widening interacts with the provider cooldown. Both of those inputs have
changed: the upstream no longer rate-limits, and the interaction is now
understood precisely enough to bound and lever rather than avoid.

## Goals / Non-Goals

- Goal: stop serializing a healthy provider route.
- Goal: give the width the same operator contract every other admission bound
  has, so the original rate-limit remedy stays available without a release.
- Goal: keep one route from consuming the whole process budget.
- Non-Goal: retune the process-wide limit, the queue wait, or the upstream
  deadline.
- Non-Goal: redesign the provider cooldown, or make the width per-provider.

## Decisions

### Decision: derive the default from process capacity, do not pick a number

The bound that still has to exist after rate limiting is gone is fairness: no
single provider route may consume the entire process budget, or one busy route
starves every other one. The narrowest statement of that is that a route may
hold at most half of process capacity, so a second route always retains at least
as much capacity as the busiest route holds. Expressed structurally,

    DEFAULT_RESPONSES_MAX_PER_ROUTE = DEFAULT_RESPONSES_MAX_CONCURRENCY // 2

which is `4` at the current process-wide limit of `8`, follows the same shape as
`DEFAULT_RESPONSES_QUEUE_TIMEOUT = DEFAULT_UPSTREAM_TIMEOUT`: retuning the
process-wide limit later moves the width with it, and no reviewer has to
rediscover why a particular number was chosen.

A derived half also keeps the specified saturation scenario reachable. `One
route saturates while process capacity remains` requires that a route can
saturate while the process limit is not binding; a width equal to the
process-wide limit would make that scenario unobservable, because the two bounds
would bind together.

Rejected alternatives:

- The process-wide limit divided by the number of manifest routes. This couples
  admission to the provider registry, so registering a provider would silently
  narrow every existing route, and it edges toward the per-provider width the
  manifest discipline forbids.
- A width one below the process-wide limit, i.e. `7`. It satisfies the
  saturation scenario by arithmetic while abandoning fairness in substance: one
  route could hold seven of eight slots.
- Removing the route semaphore entirely. It is the only thing that keeps the
  denial message able to attribute saturation to a route, and the only thing
  standing between one slow provider and the whole process budget.

### Decision: make the width a setting, not a wider constant

Simply raising the constant would deliver the latency win and leave the original
hazard unlevered: an upstream that resumes rate limiting would need a new
release to serialize its route again. Loading the width from
`CODEX_RESPONSES_PROXY_RESPONSES_MAX_PER_ROUTE` with the same `1..4096` bounds as
the process-wide limit, and rendering it from
`RuntimeContext.service_environment`, makes `=1` an operator act. This is the
lever `queue-timeout-invariant` proved is the only one a supervised install has:
a value that is not rendered into the unit cannot be reached by exporting it in a
shell.

The lower bound is deliberately `1` rather than `2` — restoring exact
single-flight is the whole point of the lever.

### Decision: assert the relationship, not the literal

The unit contract asserts that the width is greater than one and no greater than
what remains of process capacity after it:

    RESPONSES_MAX_PER_ROUTE <= RESPONSES_MAX_CONCURRENCY - RESPONSES_MAX_PER_ROUTE

This states "another route can still hold as much as this one" as a property, so
a later retune of either bound stays legal while a regression to single-flight,
or to a width that starves other routes, does not. The two behavioral contracts
were likewise rewritten against the configured width instead of the literal `1`,
which is why they hold at either width and the invariant is what pins the value.

## Risks / Trade-offs

- `transport/cooldown.remember_failure` is called only after an exchange
  returns, so at width `N` up to `N` same-route requests can reach a provider
  that has just begun rate limiting, instead of exactly one. The leak is bounded
  by the width and closes for every subsequent request once the first failure is
  recorded; `responses_rate_limited` makes it observable. This is the trade the
  operator setting exists to reverse, and the diagnosis table says so.
- A route can now occupy half the process budget, so two saturated routes can
  bind the process-wide limit where previously three could not. The denial
  message already names both limits, so the binding one stays legible.
- A supervised listener does not observe the new default until a reinstall
  re-renders its unit. That is a property of the existing projection contract.

## Migration Plan

Reinstall re-renders the unit. No state, on-disk format, or client contract
changes, so no data migration exists. Rollback is either the inverse reinstall
or `CODEX_RESPONSES_PROXY_RESPONSES_MAX_PER_ROUTE=1` in the unit's environment
followed by a reload, which restores the previous behavior exactly.

## Open Questions

None.
