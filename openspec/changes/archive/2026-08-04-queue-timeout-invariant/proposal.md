## Why

`route-slot-lease` bounded a held provider route slot by a total upstream
stream deadline of 900 seconds, and left the default local queue wait at 120
seconds. Those two numbers were chosen independently, and together they encode a
contradiction: the proxy admits that a single legitimate turn may hold its route
for up to 900 seconds, while denying any waiter that has queued for 120.

A census of the live listener's four rotated proxy logs measured the cost of
that gap directly. Across 18364 recorded route holds there were 656 queue-timeout
denials, 652 of which could be matched to the hold that blocked them. For each,
the additional wait the request actually needed was reconstructed as
`hold_end - (T - 120)`. The median was 144 seconds. The current 120-second
default therefore sits just below the median: it denies the requests that were
about to succeed. Admitting at 900 seconds would have satisfied 99.5 percent of
them. On the live listener this denial path had fired 652 times against 6391
received requests — a 10.2 percent denial rate.

`route-slot-lease` recorded that raising this default was rejected because a new
constant would reach no already-installed operator. That reasoning was wrong on
its premise and is corrected here: an install re-renders the native unit from
`RuntimeContext.service_environment`, whose queue-timeout value can only ever be
the code default, because `commands/install.py` exposes no flag for it and
`runtime_context.create` takes no such parameter. The code default is not one
lever among several — it is the only lever a supervised install has.

## What Changes

- Derive `DEFAULT_RESPONSES_QUEUE_TIMEOUT` from `DEFAULT_UPSTREAM_TIMEOUT`
  rather than restating an independent number.
- Assert the resulting invariant in the admission unit contract so the two
  constants cannot drift apart again.
- Correct the diagnosis table, which described the operator knob as the remedy
  for a default that was itself misconfigured.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=local queue wait default;
  reuse=extend; change=modify; the default queue wait is now derived from the
  total upstream stream deadline instead of being an independent constant;
  facet:lifecycle=admission; facet:surface=source,test,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- The operator override `CODEX_RESPONSES_PROXY_RESPONSES_QUEUE_TIMEOUT`, its
  validated `0.001..3600` bounds, and its projection into the native unit, all
  of which are unchanged.
- Per-route admission width, which stays single-flight at one.
- The total upstream stream deadline itself, which this change reads but does
  not retune.
- Adding an install-time flag for the queue wait.
- Live provider acceptance and the AIGW `check` and `catalog` contract.

## Impact

One runtime constant, one unit contract, the diagnosis table, and release notes
are affected. No new dependency, daemon, configuration surface, or persistent
state is added. The change is observable to an operator only after a reinstall
re-renders the native unit, because the previously installed unit pins the old
value.
