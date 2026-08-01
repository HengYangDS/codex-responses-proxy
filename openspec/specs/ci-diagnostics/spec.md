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

### Requirement: Provider projection separates source and target authority

Forge publication SHALL project one accepted content history into independent
GitLab and GitHub commit identity domains. GitLab commits SHALL use the selected
GitLab email and trust anchor. GitHub commits SHALL use the selected GitHub email
and trust anchor while preserving the canonical ordered tree history, messages,
dates, and parent topology. Publication SHALL be append-only and SHALL NOT force
update either target. Expected child failures SHALL preserve their exit status
without emitting a Python traceback.

#### Scenario: Accepted source is dev

- **WHEN** the clean canonical checkout is attached to `dev` and its current
  `HEAD` is selected for GitHub projection
- **THEN** GitHub `main` receives the equivalent GitHub-identity history
- **AND** its tip tree and ordered tree history equal the canonical source
- **AND** no canonical ref or existing provider tag is moved or rewritten.

#### Scenario: Different verified emails publish equivalent content

- **WHEN** accepted GitLab source and GitHub require different verified emails
- **THEN** their `main` commit IDs differ
- **AND** their tip tree and ordered tree history are equal
- **AND** every commit verifies under its own Forge email and trust anchor.

#### Scenario: GitHub already contains an admitted projection

- **WHEN** a later canonical GitLab commit is projected
- **THEN** the existing GitHub tip remains an ancestor of the new GitHub tip
- **AND** only the missing canonical descendants are projected
- **AND** the command emits an explicit source-to-provider mapping receipt.

#### Scenario: Target history cannot be mapped uniquely

- **WHEN** the target tip has no unique identity-neutral canonical match
- **THEN** projection fails before any ref update
- **AND** it offers no force or history-rewrite escape.

#### Scenario: Projection command rejects its invocation

- **WHEN** a provider projection child returns a nonzero status with its own
  diagnostic
- **THEN** the signing runner exits with that status
- **AND** it does not append `Traceback` or `CalledProcessError` output.

#### Scenario: Active GitLab signing key advances

- **WHEN** a provider-registered GitLab signing key replaces an unrecoverable
  predecessor for new projection commits and tags
- **THEN** the runner, projection, tag command, OpenSSH agent capability, and
  committed trust anchor select the same public-key fingerprint
- **AND** predecessor anchors remain available to verify immutable history.

