## Context

See [proposal.md](proposal.md). The product already has separate Nox sessions,
a Python-version SSOT, a native-platform asset SSOT, deterministic release
assembly, and provider-specific publication adapters. The remaining defect is
orchestration ownership: two handwritten Forge files select different subsets
and group independent proof dimensions differently.

## Goals / Non-Goals

**Goals:**

- Make proof meaning independent from Forge syntax.
- Preserve independently visible failure domains and runner-level parallelism.
- Keep the product's Python and platform matrices in their existing SSOTs.
- Make provider capability differences explicit without weakening product
  support or publication verification.
- Make generated Forge files disposable projections.
- Make the CI cutover carry the actual repository quality contract rather than
  preserve a green but materially weak rule set.
- Add reproducible performance evidence for the request data path and operator
  control path; optimize only measured bottlenecks.

**Non-Goals:**

- Require GitLab to pretend that a Windows runner exists.
- Add a generic CI framework, second task runner, or shell portability layer.
- Move product tests, platform support, signing, or release inventory into
  ETHOS.
- Make either Forge, its cache, or its artifacts the product identity owner.
- Copy ETHOS-specific governance domains, thresholds, or historical carriers
  into this smaller product merely to make the checklists look alike.

## Decisions

### Model the graph once with CUE

`.config/ci/pipeline.cue` owns proof contexts, node identifiers, dependencies,
runner capabilities, commands, and immutable third-party action/image
coordinates. CUE exports `.gitlab-ci.yml` and the GitHub verification workflow.
The repository's existing Python quality command checks that tracked
projections equal fresh exports.

CUE is already the accepted lightweight schema/projection tool in the sibling
AIGW product and provides structural constraints without introducing a runtime
framework into Proxy. YAML anchors, copied templates, and a bespoke string
rewriter were rejected because they cannot make two files one semantic owner.
Dagger was rejected because it would collapse hosted visibility back into one
large job.

### Orthogonalize language and platform proof

The review graph contains:

1. source and governance;
2. static quality at the compatibility floor;
3. one Linux test node for each supported Python line;
4. one native release-acceptance node for each available platform.

This avoids a nine-job Python-by-OS Cartesian product while proving both
language compatibility and native portability. GitLab exports the Python nodes
as `parallel:matrix`; GitHub exports `strategy.matrix`. Native Windows remains
required product evidence on GitHub. GitLab's generated projection has no
fictitious, disabled, or allowed-failure Windows job while its current runner
inventory lacks that capability.

### Keep authorization out of CI projection syntax

Developer and Maintainer admission are repository-lifecycle semantics, not
extra fields in the CI projection model. CUE owns only the checks a Forge can
actually schedule. Admission tooling and Forge branch protection own guarded
ref transitions; CI reports proof for the exact ref and commit it observes.
The two concerns share coordinates but do not share an evaluator.

The **Developer** mode requires a `proposal/*` review into `dev`. Updating the
proposal updates the existing MR/PR and runs review proof for the new head. A
plain proposal push does not run a second complete pipeline when an open review
already owns that SHA. After both selected Forges accept the exact head, a
maintainer or admitted automation advances `dev` by expected-old/exact-new
fast-forward and deletes the absorbed proposal ref.

The **Maintainer** mode may use the same review path or fast-forward an exact
locally proven commit directly to `dev`. Direct admission cannot manufacture a
pre-push hosted review. The resulting `dev` pipeline runs the product proof for
that admitted commit. A branch is never promoted while its accepted proof is
red.

The five contexts are:

1. `proposal_review`: complete product proof for an exact proposal head and
   exact `dev` base;
2. `dev_admission`: exact-ref admission followed by product proof for the
   accepted commit;
3. `main_promotion`: a `dev` to `main` MR/PR proving exact heads, ancestry,
   release readiness, and current accepted `dev` proof;
4. `main_admission`: exact-ref confirmation after the reviewed CAS
   fast-forward;
5. `release_tag`: exact signed tag and complete bundle construction, followed
   by provider-local publication, re-download, and parity proof through the
   release command rather than a second Forge-specific workflow.

### Keep publication outside Forge workflow syntax

The verification graph constructs and signs the complete native bundle once.
`python -m tools.release.publish` is the only publication composition root. Its
`github` and `gitlab` commands select one transport adapter; `both` gives the
same immutable bundle to both adapters and reports partial failure without
claiming parity. Each adapter owns only its provider API, upload, re-download,
and byte verification. Neither adapter rebuilds or re-signs product assets.

This removes the GitHub-only Release workflow instead of inventing a matching
GitLab wrapper. Forge workflows remain disposable projections of schedulable
proof; publication remains a product lifecycle operation that also works with
one Forge or from a local release workspace.

`dev` advancing while a promotion review is open makes the promotion head
stale and triggers proof for the new head. `main` advancing changes the target
base and invalidates the promotion even when the `dev` head is unchanged. The
review carrier and guarded ref update must therefore observe exact head and
base objects rather than a branch name or a green UI label alone.

GitLab can fast-forward-merge an MR, but GitHub does not offer a true
SHA-preserving PR merge mode. To keep one signed commit object on both Forges,
MRs and PRs are review carriers; the admitted transition is the same guarded
ref fast-forward on both peers. Squash, rebase, merge commits, movable tags,
and provider-authored replacement commits are invalid product transitions.

Avoiding duplicate work means eliminating duplicate event contexts. It never
means inventing an unimplemented cross-pipeline proof cache or allowing an
unreviewed maintainer push to borrow a different SHA, base, or peer result.

### Treat races and failures as state transitions

- A new proposal commit invalidates the previous review proof and runs the same
  review graph for the new SHA.
- A transient failure on unchanged source may rerun failed nodes; a source,
  workflow, lock, base, or policy change requires a new proof.
- A stale expected target ref rejects admission before mutation. The source is
  rebased onto current `dev` or a new promotion review is produced; accepted
  history is never rewritten to make a stale receipt fit.
- Dual-Forge ref updates are prepared on both peers, then applied by guarded
  fast-forward. A transport failure retries the same object. A genuine peer
  advance requires a new common product commit and new proofs; publication is
  frozen meanwhile.
- A failed direct maintainer admission is fixed forward on `dev`; it is not
  force-reset. `main` promotion remains blocked.
- Direct `main` updates are outside the normal Maintainer path. Emergency
  break-glass requires an explicit, externally auditable authorization and the
  complete missing proof; it is not a hidden CI branch.
- A release tag is created once from the exact accepted `main` commit and the
  same annotated tag object is transported to every selected Forge. Repairing
  release content creates a new version and tag rather than moving history.
- With one selected Forge or no remote, the same state machine runs over the
  available authority planes and reports its narrower scope; absence is never
  presented as dual-Forge proof.

### Preserve one bundle identity, not one physical executor

The complete bundle inventory and bytes remain the authority. A Forge may
consume an already assembled bundle or independently reproduce it, but the
publisher only accepts the exact complete signed bytes and verifies them again
after download. This resolves the false choice between independent peers and a
single Forge-owned builder: execution may differ; product identity cannot.

### Keep proof ownership local to each layer

Provider adapters own the exact hosted workflow and job identities they
normalize. The evaluator consumes only their normalized Forge-level result,
Git-object identity, complete bundle, release identity, and trust anchor. It
does not reload provider job display strings through a second policy file or
re-evaluate adapter internals. This preserves fail-closed hosted proof while
preventing a parallel publication-policy owner.

### Admit quality by risk coverage, not by a green command name

`quick` and `quality` are orchestration names, not evidence that their rule
families are sufficient. The current Ruff selection (`E4`, `E7`, `E9`, `F`) is
only a syntax/error floor and is not the terminal contract. The converged
quality graph SHALL cover the product's actual carriers and risks:

- Python correctness, modernization, imports, typing-only edges, naming,
  exceptions, logging, subprocess use, security-sensitive execution, pytest
  idioms, complexity, and performance smells;
- Ruff formatting, Ty warnings-as-errors, statement and branch coverage,
  dependency direction, dependency hygiene, unused code, semantic naming,
  commit subjects, decision records, generated-projection freshness, and
  package-only build/install evidence;
- TOML, YAML, JSON/schema, Markdown, prose, links, GitHub workflow syntax,
  secrets, OpenSpec strict validation, and repository text bytes.

Each concern has one native policy owner under `.config/checks/<concern>/` (or
the carrier's unavoidable root-native file), one reusable local command, and
CI/hook projections over that owner. A rule is admitted only when its defect
class is relevant, its false-positive cost is understood, its existing debt is
removed rather than suppressed, and the rule runs over the complete intended
inventory. Thresholds are calibrated from evidence and change risk; copying a
stricter number is not rigor.

ETHOS is a comparison source for mature mechanisms, not a configuration
template. Proxy SHALL absorb applicable mechanisms and omit ETHOS-only lane,
attestation, evidence, and governance semantics. No `noqa`, type-ignore,
warning filter, allow-failure, or broad exclude may be introduced to make a
new gate appear green.

### Prove semantic uniqueness and delete accidental structure

Every product fact and effect has one owner. A candidate duplicate is resolved
by one of four dispositions: absorb into the existing owner, rename to the
precise concept, split only along independent invariants/change reasons, or
delete when it carries no unique semantics. Compatibility facades, root
re-exports, copied Forge orchestration, provider-display-name policy, unused
configuration, and historical negative blocklists are not terminal entities.

Abstraction is admitted only for a demonstrated stable variation axis with at
least two real consumers or one required extension seam. Textual similarity is
not sufficient, and premature interfaces are not quality. The repository audit
SHALL positively declare package ownership and allowed dependency direction;
duplicate/dead-code tools are discovery aids, while deletion is justified by
consumer and behavior evidence. The acceptance question for every entity is:
what unique product value would be lost if it were removed?

### Treat performance as a measured product contract

Correctness gates do not prove performance. Proxy owns a latency- and
allocation-sensitive data path; AIGW owns interactive control paths. This
change SHALL establish reproducible baselines and explicit budgets before
claiming either is optimized.

Proxy measurements cover startup-to-ready, non-streaming request overhead,
streaming first-event overhead, sustained byte forwarding, bounded memory under
large request/stream workloads, provider-registry resolution, JSON
transformation, and zero-copy/pass-through behavior where semantically valid.
Lifecycle measurements cover status, reload/handoff interruption, and clean
shutdown. Benchmarks use deterministic local upstreams, warmup, repeated
samples, percentiles, payload-size matrices, and machine-readable output; no
third-party network latency enters the product budget.

AIGW measurements, implemented in its own repository, cover CLI cold start,
manifest parse/validate, credential lookup by backend, dry-run projection, and
atomic multi-client sync. Platform-specific native measurements remain
separate; one operating system does not prove another.

Regression budgets use a reviewed baseline artifact and statistically stable
comparison rather than one wall-clock assertion in a unit test. Profiling
(`cProfile`/allocation tracing for Python, `go test -bench`, `benchstat`, and
`pprof` for Go) follows a failed budget or explicit investigation. Optimization
must remove a measured bottleneck without weakening protocol fidelity,
security, portability, readability, or lifecycle safety.

## Risks / Trade-offs

- **GitLab has no Windows runner** → keep the capability absent from its physical
  projection, require GitHub Windows product evidence, and require GitLab to
  verify the complete Windows-containing bundle before publication.
- **A single Docker runner receives parallel matrix jobs** → the current Proxy
  runner allows multiple concurrent Docker jobs; queueing remains correct if
  host capacity is saturated and no workflow change is needed when runners are
  added.
- **Generated YAML becomes difficult to review** → review the concise CUE owner
  and enforce byte-for-byte projection freshness in quick and hosted gates.
- **Independent builds are not reproducible** → parity fails before final
  closeout; do not normalize, repackage, or re-sign divergent output.

## Migration Plan

1. Add failing workflow-contract tests for the shared graph, per-version nodes,
   tag obligations, and generated projections.
2. Add the CUE model and projection command; replace both handwritten workflow
   definitions in one cutover.
3. Map publication evidence to semantic capabilities and remove obsolete job
   names.
4. Expand the quality owner set, remediate the admitted findings without
   suppressions, and add performance baselines and budgets for the owned hot
   paths.
5. Pass focused, quick, quality, Python, performance, release, and strict
   OpenSpec gates.
6. Publish one proposal to each Forge, observe the exact review graph, promote
   the signed product commit, then exercise a successor tag.
7. Remove the superseded workflow, quality, compatibility, and benchmark
   scaffolding residue and archive this Change.
