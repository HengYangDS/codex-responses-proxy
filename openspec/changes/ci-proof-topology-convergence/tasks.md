## 1. Proof graph contract

- [x] 1.1 Add failing workflow tests that require one declarative CI owner,
  generated Forge projections, separate source/quality/Python-version/native
  nodes, and complete tag publication obligations; verify the focused tests fail
  for the current handwritten topology.
- [x] 1.2 Keep required hosted workflow and job identities in their provider
  adapters; remove the second external job-name policy and evaluator replay,
  while preserving adapter rejection of missing or duplicated required jobs.
- [x] 1.3 Keep Developer and Maintainer authorization and guarded ref admission
  in the repository lifecycle owner; remove unconsumed authorization, proof
  reuse, graph-digest, and capability fields from the CI projection model.

## 2. Declarative projections

- [x] 2.1 Add the CUE CI graph and the minimal projection command; verify fresh
  exports reproduce deterministic GitLab and GitHub YAML on repeated runs.
- [x] 2.2 Replace the GitLab aggregate Python job with a matrix of independent
  3.12, 3.13, and 3.14 jobs, plus separate source and quality nodes; verify the
  parsed pipeline exposes every required node without an aggregate `nox full`.
- [x] 2.3 Project the equivalent GitHub review graph and explicit Forge runner
  capability differences; verify actionlint and workflow contract tests pass.
- [x] 2.4 Keep tag verification and bundle construction in the CI graph, then
  publish the same pre-signed bundle through the single provider-neutral
  release command; verify each adapter uploads, re-downloads, and validates its
  own peer without treating peer CI as provider-local publication proof.
- [ ] 2.5 Verify Developer review admission, direct Maintainer admission, and
  `dev` to `main` promotion through their real lifecycle and Forge protection
  owners; reject stale or replacement-object transitions without duplicating
  those semantics in CUE.

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
