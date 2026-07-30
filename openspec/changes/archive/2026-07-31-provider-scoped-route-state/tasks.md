## 1. Incident and authority contract

- [x] 1.1 Record the canonical scoped AIGW endpoints, installed schema-v2
  unscoped route state, `route=drifted` evidence, affected source flow, and the
  absence of a current owner-correct migration command without exposing secrets.
- [x] 1.2 Validate this proposal, design, delta specification, scope, and
  authority boundary, and confirm the exact 16-path prewrite admission before
  completing implementation.

## 2. TDD regression

- [x] 2.1 Add failing tests requiring AIGW schema-v3 state to store an explicit
  `provider_route` and the matching `/dmxapi/v1`, `/ucloud/v1`, or
  `/aihubmix/v1` loopback URL while rejecting unknown routes and URL mismatches.
- [x] 2.2 Add failing adoption tests proving that the current scoped DMXAPI
  endpoint migrates schema-v2 state through `adopt-aigw`, that exact direct state
  is adoptable as disabled, and that unscoped or unrelated canonical endpoints
  remain unadopted.
- [x] 2.3 Add failing transition tests proving schema-v3 enable delegates only
  the scoped endpoint through AIGW's public CLI, disable restores the exact
  recorded direct URL, and schema-v2 AIGW state cannot re-enable `/v1`.
- [x] 2.4 Add failing controller tests for scoped non-default port discovery and
  malformed, credentialed, non-loopback, queried, fragmented, or unknown-route
  state rejection.
- [x] 2.5 Retain passing regression coverage for bounded direct-Codex `/v1`
  state, schema-v1/v2 exact disable and uninstall restoration, AIGW authority,
  and unrelated-endpoint drift refusal.
- [x] 2.6 Run the focused route and controller suites against unchanged
  production code and retain the expected RED failures before implementation.

## 3. Minimal implementation

- [x] 3.1 Add the closed provider-route allowlist and scoped URL constructor;
  advance AIGW state writing and validation to schema v3 while retaining bounded
  schema-v1/v2 readers and the separate direct-Codex legacy constructor.
- [x] 3.2 Update `adopt-aigw` to accept explicit account, provider route, and
  direct URL, atomically replace eligible schema-v2 state with schema-v3 state,
  and verify canonical status without editing AIGW configuration.
- [x] 3.3 Make AIGW enable, disable, status, and uninstall restoration consume
  only the authorized scoped schema-v3 value, except for the bounded exact
  legacy-disable path; prevent every schema-v2 re-enable to `/v1`.
- [x] 3.4 Parse installed scoped and legacy loopback URLs structurally for port
  discovery and fail closed for every unsupported URL shape.
- [x] 3.5 Run the focused suites until every new regression and all retained
  legacy, drift, and restoration contracts are GREEN.

## 4. Canonical documentation and release surfaces

- [x] 4.1 Update canonical route/authority documentation to distinguish AIGW
  provider-scoped schema-v3 state from the bounded direct-Codex `/v1` mode and
  document `adopt-aigw` as the sole schema-v2 migration entry.
- [x] 4.2 Add the route-state correction to the pending v1.0.44 release metadata
  without claiming either Forge publication, installation, or runtime recovery.
- [x] 4.3 Create the bounded claim and Chronicle record with live-state evidence,
  source proof, rollback ordering, and explicit no-session-write limits.

## 5. Complete local proof

- [x] 5.1 Run strict OpenSpec validation, release metadata, Markdown
  presentation, and release-contract checks.
- [x] 5.2 Run the repository Python quality gate with the required Ruff and Ty
  versions and retain statement and branch coverage at or above policy.
- [x] 5.3 Run the compile-and-behavior matrix on Python 3.12, 3.13, and 3.14.
- [x] 5.4 Run HEAD-bound lane status and full executed ETHOS proof without a
  weakened or scope-bypassing gate.

## 6. Successor transfer and source closeout

- [x] 6.1 Transfer final-source refresh, dual-Forge publication, protocol-v2
  installation, schema-v3 adoption, AIGW verification, and unchanged-original-
  thread acceptance into the active runtime-acceptance OpenSpec authority.
- [x] 6.2 Archive this source change after every local source task and transfer
  passes; leave governed landing, publication, installation, provider switching,
  and original-conversation recovery unclaimed here.
