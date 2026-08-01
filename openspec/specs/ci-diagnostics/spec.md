# CI diagnostics

## Purpose

Codex Responses Proxy SHALL require successful CI jobs to be free of unhandled Python
tracebacks and warnings.
## Requirements
### Requirement: Capability boundary

The CI diagnostics capability SHALL own diagnostic cleanliness across the
repository test runner, quality gate, dependency bootstrap, and provider
projections without owning application logs or provider infrastructure.
Release-contract tests SHALL verify repository-owner behavior and stable policy
values without depending on private shell syntax.

#### Scenario: A diagnostic contract changes

- **WHEN** a change alters warning, traceback, compile, cache, dependency
  bootstrap, or versioned-tool selection handling
- **THEN** the repository-owned command remains the semantic owner
- **AND** GitLab and GitHub remain thin projections over that command
- **AND** contract tests prove behavior rather than obsolete implementation text.

### Requirement: Passing test jobs have clean diagnostic output

The canonical Python test runner SHALL fail when a test returns nonzero or
emits an unhandled traceback, a `socketserver` exception banner, or a Python
warning. It SHALL use the same compile-and-test entrypoint across supported
interpreters and Forge operating systems.

#### Scenario: A passing test leaks a warning

- **WHEN** a test process exits successfully but emits a Python warning
- **THEN** the canonical runner rejects the test job
- **AND** the hosted provider cannot report that revision as verified.

### Requirement: Expected disconnects and HTTP errors retain one owner

Production handoff control SHALL close failed HTTP responses. Loopback test
fixtures MAY suppress only peer-disconnect errors caused intentionally by the
test; unrelated server exceptions SHALL remain visible.

#### Scenario: A loopback client disconnects before the upstream writes

- **WHEN** an integration test intentionally closes its client connection
- **THEN** the fixture suppresses only the resulting peer-disconnect error
- **AND** any other request-handler exception remains a failing diagnostic.

### Requirement: Quality tooling leaves no checkout cache

Compilation SHALL write bytecode below an isolated temporary prefix, and Ruff
SHALL run without a persistent checkout cache. Containerized dependency
installation SHALL explicitly select its noninteractive policy, suppress
routine package-manager chatter, and emit neither root-user nor frontend
fallback warnings.

#### Scenario: A clean quality gate completes

- **WHEN** the repository-owned quality command succeeds in hosted CI
- **THEN** no bytecode, coverage file, or Ruff cache remains in the checkout
- **AND** the job log contains no pip root-user or Debian frontend warning.

### Requirement: Platform-specific fixtures model only supported host semantics

A test fixture that depends on host shell executable-bit semantics SHALL run
only on hosts that implement those semantics, while each supported operating
system SHALL continue running its product behavior matrix.

#### Scenario: Windows runs the supported product matrix

- **WHEN** the Windows matrix evaluates quality contracts
- **THEN** POSIX shell lookup fixtures are not treated as Windows product behavior
- **AND** all Windows product tests remain enabled.

### Requirement: Quality tool identity excludes informational build metadata

The quality owner SHALL require the exact configured tool name and semantic
version while permitting only an optional space-delimited informational suffix.

#### Scenario: Stable tool reports build metadata

- **WHEN** a pinned tool reports its exact name and semantic version followed by build metadata
- **THEN** the quality owner accepts that executable
- **AND** different versions, prefixes, and malformed suffixes remain rejected.

### Requirement: GitLab main validation follows release state

The GitLab metadata verification job SHALL validate a tag pipeline against its exact tag. For an untagged main pipeline, it SHALL perform ordinary GitLab provider validation when the tag named by `VERSION` already exists and SHALL prepare a release only while that tag is absent.

#### Scenario: Main advances after publication

- **WHEN** GitLab runs an untagged main commit whose `v<VERSION>` tag already exists
- **THEN** metadata verification runs ordinary GitLab provider validation
- **AND** it does not reject the commit as an attempted duplicate release.

#### Scenario: Main carries an unpublished release candidate

- **WHEN** GitLab runs an untagged main commit whose `v<VERSION>` tag does not exist
- **THEN** metadata verification runs release preparation
- **AND** the existing pending-release chronology requirements remain enforced.

### Requirement: Reused self-hosted checkout preserves diagnostic integrity

A GitHub job on the repository's reused self-hosted runner SHALL keep a valid
pre-checkout `HEAD` reachable only for the checkout transition and SHALL remove
that temporary reachability after checkout. The workflow SHALL NOT change
runner-global Git configuration or suppress unrelated Git diagnostics.

#### Scenario: Checkout replaces an unreferenced detached revision

- **WHEN** a trusted self-hosted job starts from a detached revision that no
  branch or tag retains
- **THEN** the workflow makes that revision reachable before checkout
- **AND** checkout does not emit the abandoned-commit warning
- **AND** an always-running post-checkout step removes the temporary ref.

#### Scenario: Hosted Windows checkout is isolated

- **WHEN** the supported Windows matrix uses its hosted runner workspace
- **THEN** it continues to use the ordinary pinned checkout action
- **AND** the self-hosted temporary-ref lifecycle is not projected into that
  job.

### Requirement: Product identity is provider-neutral

The current repository, package, runtime, service, release, documentation, and
test surfaces SHALL identify the product as Codex Responses Proxy. Provider
names SHALL appear only in provider profiles, endpoints, or provider-specific
wire policies. Publication commands SHALL NOT contain a personal key path or
maintainer identity default, and SHALL fail immediately when explicit signing
inputs are unavailable.

#### Scenario: A new Responses provider is added

- **WHEN** another third-party Responses endpoint is admitted
- **THEN** it is represented as a provider profile or adapter
- **AND** no product, package, runtime, service, or environment namespace changes.

#### Scenario: Publication runs on another workstation

- **WHEN** an operator supplies provider identity and a public key available in
  an existing standard OpenSSH agent
- **THEN** the direct projector or tagger can sign without a maintainer-specific
  path, password prompt, Keychain bridge, private PTY, or temporary agent.

### Requirement: Provider identities are independent

GitLab SHALL retain accepted commits in its verified identity domain. GitHub
SHALL use its verified identity domain for an equivalent projection.

#### Scenario: Forge emails differ

- **WHEN** the two Forges require different verified emails
- **THEN** their commit IDs differ
- **AND** their corresponding trees are equal.

### Requirement: Projection continuity is append-only

A provider projection SHALL preserve messages, dates, ordered trees, and parent
topology after its admitted base and SHALL only fast-forward the target.

#### Scenario: GitHub already has an admitted base

- **WHEN** accepted source advances after the mapped GitHub tip
- **THEN** only missing descendants are projected
- **AND** the old GitHub tip remains an ancestor of the new tip.

### Requirement: Projection requires one lineage match

The projector SHALL require exactly one identity-neutral source match for an
existing provider tip before creating commits or updating refs.

#### Scenario: A target match is absent or ambiguous

- **WHEN** the provider tip has zero or multiple source matches
- **THEN** projection fails before any ref update
- **AND** it offers no force or rewrite escape.

### Requirement: Projection failures retain bounded diagnostics

The publication runner SHALL return a failed child status without adding a
Python exception traceback.

#### Scenario: A projection child rejects its invocation

- **WHEN** the child exits nonzero with its own diagnostic
- **THEN** the runner returns that status
- **AND** it emits no `Traceback` or `CalledProcessError` text.

### Requirement: Unpublished canonical descendants may converge

Accepted descendants not present on either Forge SHALL be replayed onto the
exact GitLab tip only after that tip has one identity-neutral accepted match.

#### Scenario: Accepted and GitLab histories are disconnected

- **WHEN** the histories match uniquely before unpublished accepted commits
- **THEN** only those descendants are replayed and re-signed
- **AND** duplicate-history merges and force updates remain forbidden.

### Requirement: Active GitLab signing key advances explicitly

New GitLab commits and tags SHALL use the selected registered fingerprint while
predecessor trust anchors remain available for immutable history.

#### Scenario: The active key changes

- **WHEN** a registered successor key is selected
- **THEN** runner, projection, tag command, agent, and trust input agree
- **AND** older reachable commits remain verifiable.

### Requirement: Forge history matching is linear

The GitHub projector SHALL compute each canonical and projected commit's
identity-neutral fingerprint at most once per invocation and SHALL join those
indexes without weakening publication admission.

#### Scenario: A long admitted projection gains one descendant

- **WHEN** one canonical commit follows an existing GitHub projection
- **THEN** matching work grows with the combined canonical and projected history
- **AND** it does not recompute fingerprints for every source-target pair
- **AND** the target still advances only by an ordinary fast-forward push.
