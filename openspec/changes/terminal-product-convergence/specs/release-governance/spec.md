# Spec Delta

## ADDED Requirements

### Requirement: Changelog is a release-history contract

`CHANGELOG.md` SHALL follow Keep a Changelog 1.1.0 with one leading `Unreleased`
section, canonical change categories, and released sections in descending SemVer
order. Every local product tag SHALL appear exactly once. Every released section
SHALL have a tag, except for at most one first section matching the current
untagged `VERSION` during release preparation. The exact tag, `VERSION`, first
released section, and `HEAD` SHALL agree before publication.

#### Scenario: Development continues between releases

- **WHEN** `VERSION` advances beyond the latest product tag
- **THEN** user-visible work SHALL remain under `Unreleased`
- **AND** ordinary development SHALL NOT manufacture dated release history.

#### Scenario: Release history and Git disagree

- **WHEN** a product tag lacks a released section, a historical released section
  lacks its tag, or the selected tag differs from `VERSION`, the first released
  section, or `HEAD`
- **THEN** release admission SHALL fail before construction or publication.

#### Scenario: A release commit is prepared before its tag

- **WHEN** the current untagged `VERSION` has a dated release section
- **THEN** it SHALL be the only untagged released section and the first section
  after `Unreleased`
- **AND** every older released section SHALL already correspond to a product
  tag.

### Requirement: One CI model covers every integration path

CUE SHALL own the semantic CI graph, including jobs, dependencies, triggers,
matrices, platform claims, evidence reuse, release admission, and generated
projection inventory. GitHub Actions and GitLab CI SHALL be checked projections
of that graph. Proposal review, proposal update, maintainer fast-forward, `dev`,
`main`, and tag events SHALL each produce or consume exact-revision evidence
without duplicating jobs that prove no additional fact. When both peers are
selected, each SHALL schedule the same required macOS, Linux, and Windows
functional proof outcomes with equivalent triggers, gates, thresholds,
artifacts, and exact-revision evidence. An unavailable runner blocks that peer's
completion rather than borrowing the other peer's result.

#### Scenario: A developer updates a proposal

- **WHEN** the proposal review SHA changes
- **THEN** the required review graph runs for that exact SHA
- **AND** successful merge deletes the unprotected proposal branch.

#### Scenario: A maintainer fast-forwards an admitted commit

- **WHEN** the exact commit already has reusable evidence for the unchanged
  source, locks, platform, and release context
- **THEN** the target consumes that revision-bound evidence
- **AND** any changed proof input triggers only the newly required jobs.

#### Scenario: A required branch job is skipped

- **WHEN** a `dev` or `main` review or accepted-branch event lacks any job
  required for that event, including a skipped or cancelled job
- **THEN** its stable branch admission check SHALL fail for the exact revision
- **AND** tag, release, and manual verification events SHALL NOT emit that
  required branch check.

#### Scenario: A selected peer lacks a required operating-system runner

- **WHEN** GitLab and GitHub are both selected and one cannot schedule a
  required macOS, Linux, or Windows functional proof node
- **THEN** that peer's required proof SHALL remain incomplete
- **AND** the other peer's successful job SHALL NOT satisfy it.

#### Scenario: Windows ARM64 executes general functional checks

- **WHEN** a Windows ARM64 runner executes the declared Windows functional gate
- **THEN** the evidence SHALL identify Windows ARM64 and the exact revision
- **AND** it SHALL NOT claim native Windows x86_64 ABI or asset qualification.

### Requirement: Publication closes source, Forge, and branch state

A release SHALL create one signed local commit and annotated tag object, project
those exact objects independently to selected Forges, publish complete matching
asset inventories, and retire merged proposal and delivery refs. GitHub and
GitLab MAY use different runner architectures, but neither selected peer may
omit a required operating-system functional gate. Each projection SHALL state
the architecture it actually proves and SHALL NOT relabel another platform's
evidence.

#### Scenario: A release is complete

- **WHEN** both selected Forge publications and installed-product acceptance
  pass
- **THEN** local and remote `main` and `dev` identify the accepted object
- **AND** merged proposal branches, remote `work/*`, draft releases, and failed
  unpublished intermediates have been removed.

## MODIFIED Requirements

### Requirement: Platform and Python proof nodes remain visible

When GitLab and GitHub are both selected, each provider projection SHALL expose
the same required macOS, Linux, and Windows functional proof outcomes for the
exact revision, with equivalent triggers, quality thresholds, artifact
contracts, and evidence boundaries. Each supported Python version SHALL have an
independently observable test node on each selected peer. Independent nodes
SHALL be schedulable in parallel, and one failed or missing version or platform
SHALL be identifiable without inspecting a combined multi-version job. The
platform nodes MAY use the release interpreter; a Python-version-by-platform
Cartesian matrix is not required. CPU architecture and native asset ABI
qualification SHALL remain explicit, separate facts. Native review and
protected-source nodes SHALL use distinct project-bound Runner identities,
accounts, workspaces, and caches; a tag variable or local lint SHALL NOT
establish that operational separation.

#### Scenario: Native review and accepted-source routes differ

- **WHEN** a GitLab merge request targets `dev`
- **THEN** its macOS and Windows functional nodes select review capabilities
- **AND WHEN** accepted `dev` is pushed
- **THEN** its macOS and Windows functional nodes select protected capabilities
- **AND** neither route shares a persistent native account, working root, or
  cache with the other.

#### Scenario: Platform runner is unavailable on one Forge

- **WHEN** a selected peer cannot schedule a required operating-system node
- **THEN** its CI proof SHALL remain incomplete rather than silently omit it
- **AND** another peer's success SHALL NOT substitute for that peer-local proof
- **AND** a one-peer or local-only configuration MAY report its actual narrower
  scope without claiming absent dual-peer evidence.

#### Scenario: Windows ARM64 runs functional proof

- **WHEN** a selected peer runs general Windows checks on an ARM64 VM
- **THEN** those checks MAY satisfy the declared Windows functional outcome
- **AND** their evidence SHALL retain the ARM64 architecture
- **AND** the physical host observation alone SHALL NOT establish the program
  ABI
- **AND** asset acceptance MAY separately qualify `windows-x86_64` when the
  actual built executable and interpreter use `win-amd64` and the full native
  lifecycle passes; native ARM64 execution SHALL NOT be claimed.

#### Scenario: Linux review tags resolve without recursive aliases

- **WHEN** GitLab selects a Linux merge-request or accepted-source proof node
- **THEN** each job SHALL reference its review or protected native scheduling
  variable directly, with no workflow-to-job alias expansion
- **AND** both routes SHALL share the same CUE-owned functional job body.
