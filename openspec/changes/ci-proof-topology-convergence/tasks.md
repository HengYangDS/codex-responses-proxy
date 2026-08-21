## 1. Proof graph contract

- [ ] 1.1 Add failing workflow tests that require one declarative CI owner,
  generated Forge projections, separate source/quality/Python-version/native
  nodes, and complete tag publication obligations; verify the focused tests fail
  for the current handwritten topology.
- [ ] 1.2 Define semantic publication capabilities independently from provider
  display names; verify evaluator and adapter tests reject missing or duplicated
  capabilities.
- [ ] 1.3 Encode Developer and Maintainer authorization separately from
  proposal-review, dev-admission, main-promotion, main-admission, and tag proof;
  verify proposal updates, direct Maintainer fast-forwards, stale heads/bases,
  and exact proof reuse all fail closed at the correct boundary.

## 2. Declarative projections

- [ ] 2.1 Add the CUE CI graph and the minimal projection command; verify fresh
  exports reproduce deterministic GitLab and GitHub YAML on repeated runs.
- [ ] 2.2 Replace the GitLab aggregate Python job with a matrix of independent
  3.12, 3.13, and 3.14 jobs, plus separate source and quality nodes; verify the
  parsed pipeline exposes every required node without an aggregate `nox full`.
- [ ] 2.3 Project the equivalent GitHub review graph and explicit Forge runner
  capability differences; verify actionlint and workflow contract tests pass.
- [ ] 2.4 Give both tag projections exact tag, complete bundle, provider-local
  publish, re-download, and byte-verification responsibilities; verify neither
  projection treats peer CI success as provider-local publication proof.
- [ ] 2.5 Add exact same-Forge proof resolution for `dev` admission and guarded
  `dev` to `main` promotion; reuse only matching head/base/graph/capability
  evidence, execute missing proof for direct Maintainer admission, and reject
  non-fast-forward or replacement-object transitions.

## 3. Governance and closeout

- [ ] 3.1 Update release policy, Forge operations, DR-0004, and the main
  release-governance specification; verify docs and strict OpenSpec validation
  pass without contradictory build-once or provider-asymmetric language.
- [ ] 3.2 Replace the syntax-only Ruff floor with the reviewed applicable rule
  families; add native owners for type, docstring, import/dependency, dead-code,
  configuration, Markdown/prose/link, workflow, secret, OpenSpec, build/install,
  and repository-hygiene concerns; repair findings without suppressions.
- [ ] 3.3 Audit every source, test, tool, config, documentation, release, and
  Forge carrier for duplicate authority, dead consumers, facades, and obsolete
  compatibility; resolve each finding by absorb, precise rename, semantic split,
  or deletion and verify allowed dependency direction remains acyclic.
- [ ] 3.4 Add deterministic Proxy performance benchmarks and reviewed budgets
  for startup, request/stream overhead, forwarding throughput, large-payload
  memory, registry resolution, protocol transforms, status, and handoff; record
  machine-readable repeated evidence and profile only failed metrics.
- [ ] 3.5 Run focused workflow/publication tests, complete quality graph, Python
  3.12/3.13/3.14, performance, native release, and strict OpenSpec gates without
  warnings or suppressions.
- [ ] 3.6 Publish the exact signed proposal commit to both Forges and verify the
  observed MR/PR graphs bind every required node to that commit.
- [ ] 3.7 Exercise both authorization modes: admit the reviewed exact proposal
  head and separately prove the Maintainer direct-`dev` fallback does not reuse
  absent or stale review evidence.
- [ ] 3.8 Open `dev` to `main` promotion reviews on both Forges, prove the exact
  head/base pair, and advance both `main` refs by guarded fast-forward of the
  same signed commit object.
- [ ] 3.9 Archive the completed Change, promote the same signed product commit,
  publish a successor release tag, and verify local/GitLab/GitHub commit, tag,
  complete release bytes, and provider-local pipeline evidence converge.
