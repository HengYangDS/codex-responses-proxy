## Context

See `proposal.md` for motivation. The repository already owns Ruff, ty,
coverage, dependency, dead-code, secret, link, workflow, OpenSpec, architecture,
commit, and release checks, but their scopes and composition are incomplete.
Some checks are tool-native, some are repository-semantic, and some are only
indirectly asserted by tests. The terminal design must strengthen coverage
without creating a second orchestration language or turning descriptive source
metrics into arbitrary vetoes.

## Goals / Non-Goals

**Goals:**

- One machine-readable responsibility map assigns each quality concern to its semantic owner,
  governed carriers, execution command, and applicability rationale.
- Tool-native configurations own syntax-level policy; Python owns only the
  cross-file and product-semantic checks that native tools cannot express.
- Product code, tooling, tests, prose, configuration, CI, packaging, and native
  platform behavior receive appropriately strict—not blindly identical—checks.
- One Nox composition root is projected into hooks and both Forges.
- Diagnostics and warnings are errors when the repository can act on them.

**Non-Goals:**

- Requiring test functions to repeat their contract in ornamental docstrings.
- Enabling mutually incompatible formatter rules or rules whose signal is
  already owned more precisely by another gate.
- Adding baseline files, blanket exclusions, path-specific waivers, or a list of
  historical bad strings.
- Claiming native Windows or Linux acceptance from macOS mocks.

## Decisions

### Policy is organized by responsibility, not by tool

The canonical responsibility map describes concerns and scopes. Ruff, ty, coverage,
dependency analysis, and prose/configuration tools are implementations of those
concerns. This prevents a tool upgrade or replacement from changing product
semantics accidentally. A tool-centric checklist was rejected because it makes
"all rules enabled" look complete while leaving non-Python surfaces uncovered.

### Native tools are preferred; custom Python is the semantic seam

Formatting, linting, typing, dependency hygiene, dead code, secrets, workflow
syntax, links, and structured-file validation use mature tools. Custom code is
retained only for repository topology, product identities, cross-carrier SSOT,
and other constraints no native tool owns. Adding more textual blacklist tests
was rejected because it encodes history instead of the desired state.

Mature runtime frameworks are evaluated by the same rule. DR-0006 records why
FastAPI does not replace this product's native ingress and handoff boundary, and
why HTTPX is admitted for a subsequent bounded upstream-transport migration
only after it proves deletion, raw-byte parity, frozen-distribution support, and
three-platform behavior.

### Applicability is positive and role-aware

Each carrier belongs to a role such as product, repository tool, test, prose,
configuration, or generated projection. Rules are selected for the risk of that
role. Public product and tool APIs require complete documentation, while ty
owns sound typing for every Python role. Test names and assertions are their
documentation contract and do not require duplicate docstrings. Explicit role
selection was chosen over broad ignores and inline suppression.

### Thresholds require a risk model

Coverage, complexity, size, performance, and retry/time budgets are blocking
only when their owner states the protected risk, measurement, false-positive
cost, remediation, and review trigger. Metrics without a defensible threshold
remain visible observations. "Tighter is always better" was rejected because an
unreachable threshold rewards gaming rather than product quality.

### One executable graph, multiple projections

Nox composes the repository-owned graph. Local commands, hooks, GitHub, and
GitLab invoke named Nox sessions; Forge files do not copy command bodies. CUE
validates that projections remain isomorphic. Platform jobs may differ only in
runner-native setup and the capability they prove.

## Risks / Trade-offs

- [Initial diagnostics are numerous] -> Land by concern with focused tests and
  run the heavy graph once after each coherent batch.
- [Strict typing exposes third-party stub uncertainty] -> Narrow values at the
  boundary; do not use `Any`, casts, or suppressions as a substitute for proof.
- [Role-specific rules can drift] -> Validate the responsibility map against tracked files
  and reject uncovered or multiply owned carriers.
- [A tool lacks a supported-platform binary] -> Keep product proof portable and
  replace the tool or scope it to a non-product projection; do not weaken the
  product capability claim.

## Migration Plan

1. Record the current tool, rule, and surface inventory and executable gap inventory.
2. Establish the canonical responsibility map and contract tests before changing tool
   configuration.
3. Enable one concern at a time, repair all diagnostics in its declared scope,
   and remove superseded custom checks.
4. Project the final graph into hooks and both Forges from the CUE owner.
5. Run focused checks, the full Python matrix, release construction, OpenSpec
   strict validation, and native platform evidence before archive.

Rollback is a normal Git revert of the complete atom. No runtime or user-state
migration is involved.
