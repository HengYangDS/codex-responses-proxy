## Why

The repository currently proves several important quality concerns, but the
implemented graph is not yet a complete description of the product's quality
contract. Passing the present gate can therefore coexist with unchecked type
unsoundness, incomplete public documentation, configuration drift, or a
provider-specific CI projection that does not exercise the same owner.

## What Changes

- Replace the partial rule list with a responsibility-driven quality map for
  product code, repository tooling, tests, documentation, configuration,
  security, dependencies, release construction, and supported platforms.
- Make every blocking rule identify its risk, scope, measurement, remediation,
  false-positive cost, and review condition in one tracked policy owner.
- Tighten import normalization, public API documentation, type soundness,
  complexity, dependency direction, dead-code, security, prose, configuration,
  commit, CI, and release checks without blanket suppressions or historical
  forbidden-item lists.
- Require local development, hooks, Nox, GitHub, and GitLab to invoke the same
  repository-owned graph rather than restating its commands.
- Treat macOS, Linux, and Windows behavior as separately proved capabilities;
  syntax-only or mock-only checks cannot stand in for native product evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `quality-boundaries`: define complete, role-aware quality coverage and the
  evidence required for every enforced or intentionally inapplicable rule.
- `release-governance`: require every local and hosted execution plane to
  consume the same repository-owned quality graph.

## Impact

This changes the tracked quality policies, Nox composition, quality tooling,
tests, contribution documentation, hook expectations, and both Forge
projections. Existing source and tests will be mechanically normalized or
refactored where the new contract exposes real defects. It does not change the
proxy protocol, provider behavior, user credentials, installed service, or
Codex-owned state.
