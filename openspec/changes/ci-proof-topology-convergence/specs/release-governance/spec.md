## MODIFIED Requirements

### Requirement: Validation follows authorization and lifecycle state

The repository SHALL expose one provider-neutral CI graph for the checks that
GitLab and GitHub actually schedule. Developer and Maintainer authorization,
guarded ref admission, publication, and parity SHALL remain in their existing
repository-lifecycle owners rather than being redeclared as unconsumed CI
fields. GitLab and GitHub SHALL project the same required proof nodes from the
CI graph. A provider projection MAY omit only a native platform whose runner
capability is explicitly unavailable; that omission SHALL remain visible and
SHALL NOT be interpreted as product-level platform evidence.

Each supported Python version SHALL have an independently observable test node.
Independent nodes SHALL be schedulable in parallel and one failed version or
platform SHALL be identifiable without inspecting a combined multi-version
job. A Forge SHALL NOT collapse source governance, quality, the supported
Python matrix, native product acceptance, or publication into one aggregate
verification node.

#### Scenario: Ordinary test in an untagged checkout

- **WHEN** the product test suite validates repository metadata outside a
  review or tag pipeline
- **THEN** it SHALL use ordinary provider-neutral validation
- **AND** it SHALL NOT assume that the current release tag is absent.

#### Scenario: Reviewed source change

- **WHEN** an MR or PR evaluates a proposed product commit
- **THEN** source governance, quality, Python 3.12, Python 3.13, Python 3.14,
  and every available native-platform proof SHALL be separate visible nodes
- **AND** the nodes SHALL bind to the exact proposed product commit
- **AND** a proposal branch push SHALL NOT run a duplicate complete proof.

#### Scenario: Proposal changes after review failure

- **WHEN** a Developer pushes a new commit to a proposal with an open MR or PR
- **THEN** the review event SHALL evaluate the new exact head SHA
- **AND** no success attached only to the previous head SHALL satisfy it
- **AND** the ordinary proposal push SHALL NOT create a duplicate complete
  branch pipeline for that same lifecycle context.

#### Scenario: Developer admission to dev

- **WHEN** an exact proposal head has complete review proof on a selected Forge
- **THEN** the repository lifecycle owner SHALL require the reviewed head to
  descend from the current exact `dev` head
- **AND** that owner SHALL advance `dev` only by guarded fast-forward
- **AND** the absorbed proposal ref SHALL be deleted after successful admission
- **AND** squash, rebase, merge-commit, or provider-authored replacement objects
  SHALL NOT be accepted as the reviewed product commit.

#### Scenario: Maintainer admission to dev

- **WHEN** a Maintainer fast-forwards a locally proven commit directly to `dev`
- **THEN** the `dev` pipeline SHALL execute complete product proof for the
  admitted exact commit
- **AND** failed admission SHALL block promotion and be repaired by a new
  forward commit rather than history rewrite.

#### Scenario: Accepted branch projection

- **WHEN** a reviewed commit is absorbed into `dev`
- **THEN** the branch pipeline SHALL confirm exact accepted-source identity and
  release metadata
- **AND** it SHALL execute the declared accepted-branch proof without consulting
  an undeclared cross-pipeline cache.

#### Scenario: Promotion from dev to main

- **WHEN** a Maintainer opens or updates a `dev` to `main` MR or PR
- **THEN** the promotion proof SHALL bind the exact `dev` head and exact `main`
  base
- **AND** it SHALL require `main` to be an ancestor of `dev`
- **AND** it SHALL require current accepted `dev` proof and release readiness
- **AND** the repository lifecycle owner SHALL advance `main` only by guarded
  fast-forward of the reviewed `dev` commit.

#### Scenario: Promotion head or base changes

- **WHEN** `dev` changes while promotion is open, or the exact `main` base
  changes before admission
- **THEN** the previous promotion proof SHALL become stale
- **AND** the new head/base pair SHALL be evaluated before `main` changes.

#### Scenario: Accepted main projection

- **WHEN** the reviewed `dev` commit is admitted to `main`
- **THEN** the branch pipeline SHALL confirm source identity and release
  metadata for the exact accepted commit
- **AND** the repository lifecycle owner SHALL retain responsibility for the
  guarded ref transition and promotion authorization.

#### Scenario: Direct main mutation

- **WHEN** an actor attempts to update `main` without current promotion proof
- **THEN** the normal lifecycle SHALL reject the transition
- **AND** an emergency exception SHALL require explicit auditable break-glass
  authorization and the complete missing proof rather than an implicit
  Maintainer bypass.

#### Scenario: Pre-tag preparation

- **WHEN** the release owner prepares a new immutable tag
- **THEN** `--prepare-release` SHALL require the current version tag to be
  absent.

#### Scenario: Tagged release checkout

- **WHEN** a Forge evaluates an existing release tag
- **THEN** it SHALL verify the exact annotated tag and source identity
- **AND** it SHALL build or consume every supported native platform asset
- **AND** it SHALL verify its provider-local publication and re-downloaded
  bytes
- **AND** it SHALL NOT substitute a successful peer pipeline for its own
  publication proof.

#### Scenario: Dual-Forge admission race

- **WHEN** both selected Forges are prepared to advance an accepted ref
- **THEN** each update SHALL compare the observed target head and fast-forward
  the same product commit
- **AND** a transport failure MAY retry the unchanged object
- **AND** a genuine target advance SHALL invalidate stale proof and block
  publication until a new common product commit is proven.

#### Scenario: Reduced authority topology

- **WHEN** the repository operates with one selected Forge or with no remote
- **THEN** the same lifecycle invariants SHALL apply to the available authority
  planes
- **AND** the result SHALL state its exact local or one-Forge scope
- **AND** it SHALL NOT claim absent dual-Forge evidence.

#### Scenario: Forge verifies the product tag

- **WHEN** a Forge tag pipeline verifies the published product object
- **THEN** it SHALL supply only the repository, exact tag, and external trust
  anchor
- **AND** it SHALL NOT add a Forge identity to the verifier grammar.

#### Scenario: Platform runner is unavailable on one Forge

- **WHEN** a selected Forge has no admitted runner for a supported native
  platform
- **THEN** its projection SHALL expose that capability gap in the declarative
  topology
- **AND** another Forge's native-platform proof MAY establish product support
- **AND** the selected Forge SHALL still verify the complete immutable bundle
  before claiming provider-local publication.

### Requirement: Dual-Forge releases project one complete signed bundle

The release owner SHALL define exactly one complete release-bundle identity for
each version. Each selected Forge SHALL publish and re-download the exact same
files, and dual-Forge parity SHALL require equal complete inventories, bytes,
checksum manifest, signature, and trust-anchor digest. Independent deterministic
construction is permitted only when it reproduces that exact bundle identity;
it does not authorize provider-specific packaging or signing semantics.

#### Scenario: Complete parity

- **WHEN** GitLab and GitHub both publish a release tag
- **THEN** each release SHALL contain every archive and manifest named by the
  supported platform SSOT plus `SHA256SUMS` and `SHA256SUMS.sig`
- **AND** every corresponding byte digest SHALL be identical
- **AND** both releases SHALL report the same product trust-anchor digest.

#### Scenario: Provider reproduces the bundle independently

- **WHEN** a Forge constructs release files from the same signed source object
- **THEN** the resulting complete bundle SHALL match the canonical bundle
  identity byte for byte
- **AND** any nondeterministic or provider-specific result SHALL fail before
  publication.

#### Scenario: Incomplete or independently signed projection

- **WHEN** either Forge omits a platform, changes any file, regenerates a
  different checksum inventory, re-signs with a different identity, or reports
  a different trust anchor
- **THEN** publication parity SHALL fail closed
- **AND** the incomplete release SHALL NOT be installation authority.

#### Scenario: Optional peer unavailable

- **WHEN** one Forge is unavailable
- **THEN** the other Forge MAY publish the unchanged complete bundle
- **AND** the result SHALL be reported as one-sided publication rather than
  dual-Forge parity.

### Requirement: CI projects the complete repository quality contract

The repository SHALL own one explicit quality graph whose concerns cover every
tracked source, test, configuration, documentation, specification, workflow,
and release carrier relevant to the product. Local commands, hooks, GitLab, and
GitHub SHALL project the same concern owners. A successful partial rule set
SHALL NOT be represented as complete repository quality.

#### Scenario: Python quality is evaluated

- **WHEN** repository Python is admitted
- **THEN** formatting, correctness, modernization, imports, typing, naming,
  exceptions, logging, subprocess safety, security-sensitive execution, pytest
  idioms, complexity, and performance-smell rules SHALL be evaluated
- **AND** type diagnostics and warnings SHALL fail the gate
- **AND** source or test suppressions SHALL NOT be used to satisfy newly
  admitted rules.

#### Scenario: Non-Python carriers are evaluated

- **WHEN** repository quality executes
- **THEN** TOML, YAML, JSON/schema, Markdown, prose, links, workflow syntax,
  secrets, OpenSpec, generated projections, semantic names, commit subjects,
  decision records, dependency direction, dependency hygiene, package build,
  installed artifact behavior, and text-byte invariants SHALL each have an
  explicit owner or an explicit product-irrelevance decision
- **AND** each admitted concern SHALL run over its complete declared inventory.

#### Scenario: A stricter rule is proposed

- **WHEN** a rule family or threshold is added or tightened
- **THEN** its defect class, scope, false-positive cost, remediation, and review
  condition SHALL be declared
- **AND** existing findings SHALL be repaired or the rule SHALL remain visibly
  pending
- **AND** copying another repository's number or configuration SHALL NOT itself
  establish suitability.

### Requirement: Product semantics have one minimal implementation

Every authoritative fact and effect SHALL have one semantic owner. Modules,
commands, adapters, policies, projections, and compatibility surfaces SHALL be
retained only when they carry unique product value. Shared abstractions SHALL
correspond to a stable variation axis rather than textual similarity.

#### Scenario: Parallel or redundant implementation is found

- **WHEN** two carriers own the same fact or behavior, or one carrier has no
  current consumer
- **THEN** the terminal disposition SHALL be absorb, precise rename, semantic
  split, or deletion
- **AND** a forwarding facade, copied policy, negative blocklist, or dormant
  compatibility path SHALL NOT remain after callers migrate.

#### Scenario: Shared abstraction is proposed

- **WHEN** common behavior appears in multiple places
- **THEN** extraction SHALL require a demonstrated stable invariant and real
  consumers
- **AND** dependency direction and public surface SHALL remain narrower after
  extraction
- **AND** no abstraction SHALL be introduced solely to reduce line similarity.

### Requirement: Performance claims are reproducible and budgeted

The product SHALL publish deterministic local benchmarks and reviewed budgets
for request-path and lifecycle overhead. Performance acceptance SHALL use
machine-readable repeated measurements isolated from third-party network
latency. A passing functional suite SHALL NOT be described as performance
optimization evidence.

#### Scenario: Proxy data path is measured

- **WHEN** performance acceptance runs
- **THEN** startup readiness, non-streaming overhead, streaming first-event
  overhead, sustained forwarding, large-payload memory, route resolution, and
  protocol transformation SHALL be measured over declared payload sizes
- **AND** results SHALL include repeated samples and percentile or distribution
  evidence
- **AND** the benchmark upstream SHALL be deterministic and local.

#### Scenario: Performance regresses

- **WHEN** a measured metric exceeds its reviewed budget or allowed baseline
  delta
- **THEN** the gate SHALL fail with the exact metric and comparison
- **AND** profiling SHALL identify the bottleneck before implementation changes
- **AND** correctness, security, portability, and lifecycle guarantees SHALL not
  be weakened to recover the number.
