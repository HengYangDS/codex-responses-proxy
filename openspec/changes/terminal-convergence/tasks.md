# Tasks

## 1. Authority and inventory

- [x] 1.1 Record exact current heads, leases, worktrees, dirty overlays, and independent Forge state.
- [ ] 1.2 Classify every historical lane as absorbed, uniquely useful, or discardable.
- [ ] 1.3 Rebuild only unique product semantics in this terminal lane; never merge an old tree wholesale.

## 2. Runtime correctness

- [x] 2.1 Prove rollback removes verified candidate-only files and preserves prior and unknown content.
- [x] 2.2 Prove `store=false` and provider-portable replay across UCloud, DMXAPI, and AIHubMix.
- [x] 2.3 Prove bounded DMXAPI empty-response and non-text agent-content recovery.
- [x] 2.4 Prove provider-scoped 429 backpressure and client-owned conversation concurrency.

## 3. Product and repository quality

- [ ] 3.1 Remove compatibility shells, forwarding facades, hard-coded host identity, paths, and Forge coupling.
- [ ] 3.2 Converge semantic packages, UX/DX surfaces, docs, decisions, and configuration SSOTs.
- [ ] 3.3 Refresh the latest stable locked supply chain without duplicated CI pins.
- [x] 3.4 Prove formatting, lint, typing, security, links, architecture, release, and all supported platforms.
- [x] 3.5 Prove statement, branch, and package coverage are each strictly above 95%.

## 4. Delivery and acceptance

- [ ] 4.1 Archive the completed change, execute full proof, and land the exact revision.
- [ ] 4.2 Close `candidate/dev`, accepted `dev`, and release `main` through public governance commands.
- [ ] 4.3 Publish matching signed assets independently to GitLab and GitHub and verify each Forge separately.
- [ ] 4.4 Install the formal asset and verify native lifecycle and runtime health.
- [ ] 4.5 Verify three-provider switching and continuous reply in the original Codex conversation without modifying its stored state.
- [ ] 4.6 Verify PyCharm MCP remains healthy as an independent surface.

## 5. Housekeeping

- [ ] 5.1 Retire every absorbed or discarded worktree, branch, and lease with owner-bound evidence.
- [ ] 5.2 Remove old services, temporary checkouts, caches, and generated residue.
- [ ] 5.3 Recheck canonical roots, protected branches, CI, releases, installation, runtime, and zero remaining next actions.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `runtime-upgrade:Rollback owns only current product files` | `2.1` | `tests/lifecycle/test_transaction.py::test_upgrade_rollback_removes_candidate_only_runtime_members` |
| `provider-portable-responses:Provider switching is stateless` | `2.2` | `tests/protocol/test_request_history.py; tests/relay/test_transport_failures.py` |
| `provider-portable-responses:Upstream failure recovery preserves agent semantics` | `2.3` | `tests/relay/test_empty_response.py; tests/relay/test_input_recovery.py; tests/relay/test_relay.py` |
| `provider-portable-responses:Backpressure is provider-scoped` | `2.4` | `tests/relay/test_rate_limit_transport.py` |
| `repository-organization:Physical structure follows semantic ownership` | `3.2` | `tests/quality/test_contract.py` |
| `repository-organization:User and developer interfaces remain distinct` | `3.2` | `tests/cli; tests/release` |
| `quality-boundaries:Supply-chain versions have one maintained authority` | `3.3` | `uv lock --check; tests/forge` |
| `quality-boundaries:Quality evidence covers the complete product surface` | `3.4` | `nox -s quality tests-3.12 tests-3.13 tests-3.14 release` |
