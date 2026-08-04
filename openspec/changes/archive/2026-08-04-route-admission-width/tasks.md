## 1. The width becomes a setting

- [x] 1.1 Add a RED unit contract asserting the per-route width is greater than
  one and leaves at least as much process capacity for another route; observe
  the RED.
- [x] 1.2 Add `RESPONSES_MAX_PER_ROUTE_ENV`, a `1..4096` validated
  `responses_max_per_route` setting, and a default derived from
  `DEFAULT_RESPONSES_MAX_CONCURRENCY`; source `admission.RESPONSES_MAX_PER_ROUTE`
  from it; obtain focused GREEN.
- [x] 1.3 Render the setting from `RuntimeContext.service_environment` so
  restoring single-flight is an operator act rather than a release.

## 2. Contracts written against the width

- [x] 2.1 Rewrite the route-saturation and waiting-request admission contracts
  against the configured width instead of the literal one.
- [x] 2.2 Rewrite the 503 message contract so the reported route limit is
  proved to follow the configured width rather than a hardcoded one: saturate at
  a patched width of one, then report under a distinct patched width of three.
- [x] 2.3 Extend the unit-projection and settings-validation contracts to cover
  the new variable, including its rejection of a non-positive value.

## 3. Verification

- [x] 3.1 Run full quality with statement and branch coverage above 95 percent.
- [x] 3.2 Confirm no source, test, or document still asserts per-route
  single-flight as a standing contract.

## 4. Post-archive acceptance boundary

The following are live-system claims. They remain open after this repository
change is archived and must not be marked complete by OpenSpec archival.

- A reinstall must re-render the native unit so a supervised listener actually
  observes the new width.
- A live route must be observed holding more than one concurrent exchange, with
  `active=` exceeding one for a single provider on the live listener.
- `responses_rate_limited` must stay at zero, which is the standing evidence
  that the upstream rate limiting that originally justified single-flight has
  not returned. If it grows, the recorded remedy is
  `CODEX_RESPONSES_PROXY_RESPONSES_MAX_PER_ROUTE=1`, not a revert.
