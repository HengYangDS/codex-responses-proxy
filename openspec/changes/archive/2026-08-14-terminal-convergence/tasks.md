# Tasks

## 1. Authority and inventory

- [x] 1.1 Record exact current heads, leases, worktrees, dirty overlays, and independent Forge state.
- [x] 1.2 Classify every historical lane as absorbed, uniquely useful, or discardable.
- [x] 1.3 Rebuild only unique product semantics in this terminal lane; never merge an old tree wholesale.

## 2. Runtime correctness

- [x] 2.1 Prove rollback removes verified candidate-only files and preserves prior and unknown content.
- [x] 2.2 Prove `store=false` and provider-portable replay across UCloud, DMXAPI, and AIHubMix.
- [x] 2.3 Prove bounded DMXAPI empty-response and non-text agent-content recovery.
- [x] 2.4 Prove provider-scoped 429 backpressure and client-owned conversation concurrency.

## 3. Product and repository quality

- [x] 3.1 Remove compatibility shells, forwarding facades, hard-coded host identity, paths, and Forge coupling.
- [x] 3.2 Converge semantic packages, UX/DX surfaces, docs, decisions, and configuration SSOTs.
- [x] 3.3 Refresh the latest stable locked supply chain without duplicated CI pins.
- [x] 3.4 Prove the repository-owned formatting, lint, typing, security, links, architecture, release, and supported-platform contracts locally.
- [x] 3.5 Prove statement, branch, and package coverage are each strictly above 95%.

## Delivery boundary

Archiving, exact-HEAD proof, branch-role transitions, independent Forge
publication, formal installation, runtime and original-conversation acceptance,
PyCharm MCP observation, and lane retirement are post-Change lifecycle effects.
Their public command receipts and the active delivery Goal own those facts;
duplicating them here would make Change completion depend on its own archive
operation.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `runtime-upgrade:Rollback owns only current product files` | `2.1` | `tests/lifecycle/test_transaction.py::test_upgrade_rollback_removes_candidate_only_runtime_members` |
| `provider-portable-responses:Every Responses request is projected to a provider-portable form` | `2.2` | `tests/protocol/test_request_history.py; tests/relay/test_transport_failures.py` |
| `provider-portable-responses:Portable dialogue and tool relationships are preserved` | `2.3` | `tests/relay/test_empty_response.py; tests/relay/test_input_recovery.py; tests/relay/test_relay.py` |
| `provider-portable-responses:Provider-specific recovery is route-scoped` | `2.3` | `tests/relay/test_empty_response.py; tests/relay/test_transport_failures.py` |
| `provider-portable-responses:Provider rate limits do not multiply across retry layers` | `2.4` | `tests/relay/test_rate_limit_transport.py` |
| `provider-portable-responses:Ordinary concurrency remains outside the proxy` | `2.4` | `tests/relay/test_rate_limit_transport.py; tests/relay/test_relay.py` |
| `quality-boundaries:One structural quality boundary` | `3.2` | `tests/quality/test_contract.py` |
| `repository-organization:Portable product and repository UX` | `3.2` | `tests/cli; tests/release` |
| `ci-diagnostics:Supply-chain pins are current and reproducible` | `3.3` | `uv lock --check; tests/forge` |
| `ci-diagnostics:Verification has one repository-owned owner` | `3.4` | `nox -s quick quality release` |
| `ci-diagnostics:Coverage is strict and host-independent` | `3.4` | `nox -s quality tests-3.12 tests-3.13 tests-3.14 release` |
