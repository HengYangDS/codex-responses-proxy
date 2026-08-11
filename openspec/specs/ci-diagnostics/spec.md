# Verification Diagnostics

## Purpose

Define one repository-owned verification graph whose successful output is
quiet, reproducible, cross-platform, and sufficient to reject incomplete
product or release candidates.
## Requirements
### Requirement: Verification has one repository-owned owner

Nox SHALL own the verification graph, the committed uv lock SHALL own Python
tool resolution, and project metadata SHALL declare the exact current stable uv
bootstrap used by local and hosted verification. A pending release heading SHALL
match `VERSION` and the current UTC date before either Forge prepares a release.

#### Scenario: A clean checkout is verified

- **WHEN** a contributor or Forge installs the declared uv bootstrap and runs
  the repository command
- **THEN** the lock supplies every runtime and quality dependency
- **AND** Nox resolves the Python matrix from `.python-versions`
- **AND** no ambient user site, another repository environment, or unpinned
  package resolution contributes to success.

#### Scenario: Release preparation crosses a UTC date boundary

- **WHEN** a pending version has not been tagged and its Changelog date is no longer the current UTC date
- **THEN** release preparation fails closed
- **AND** the heading is advanced before proof, tagging, or publication.

#### Scenario: Provider-native tags are checked

- **WHEN** GitLab or GitHub validates release history
- **THEN** the provider checks its own reachable SemVer tags and corresponding
  Changelog headings
- **AND** tag creation time is not required to equal the Changelog date
- **AND** the two publication planes remain independently verifiable.

#### Scenario: GitLab runs a repository Python tool

- **WHEN** a GitLab job invokes release or quality Python code
- **THEN** it runs through `uv run --locked --no-sync`
- **AND** no ambient interpreter or uninstalled runtime dependency contributes
  to the result.

#### Scenario: GitLab project coordinates contain namespaces

- **WHEN** runner admission queries a project whose coordinate contains `/`
- **THEN** the coordinate is encoded as one GitLab project identifier
- **AND** the runner API request resolves the intended project rather than a
  truncated path.

#### Scenario: The uv bootstrap advances

- **WHEN** the current stable uv patch is available
- **THEN** project metadata and its executable contract name that same exact version
- **AND** the dependency lock and product runtime semantics remain unchanged.

### Requirement: Successful verification output is pristine

Passing tests, quality checks, builds, and expected operational-failure probes
SHALL emit no unhandled traceback, warning, `socketserver` exception banner,
package-install warning, false success, or private path. Expected peer
disconnects MAY be suppressed only by the fixture that creates them.

#### Scenario: A test leaks a warning or server exception

- **WHEN** the underlying process exits zero but emits an unhandled warning or
  exception banner
- **THEN** the repository-owned gate fails
- **AND** a Forge cannot report that revision as verified.

#### Scenario: A clean gate succeeds

- **WHEN** quick, quality, matrix, or release verification completes
- **THEN** its log ends with one concise receipt
- **AND** the checkout contains no bytecode, coverage, Ruff, or build cache
  created by that gate.

### Requirement: Python compatibility and native release prove distinct facts

Each supported Python minor line SHALL build and install the wheel, then run
the complete non-native behavior inventory. The release session SHALL be the
only native executable build owner and SHALL black-box test the target-platform
executable with Python absent from the product `PATH`.

#### Scenario: The supported matrix runs

- **WHEN** Python 3.12, 3.13, and 3.14 sessions execute
- **THEN** each tests the installed wheel rather than source-import fallback
- **AND** hosted jobs select minor release lines rather than one host-specific
  patch build
- **AND** platform-specific integration runs only on the platform that owns the
  real system call while synthetic wire fixtures remain portable.

#### Scenario: A native asset is accepted

- **WHEN** the release session packages a supported platform archive
- **THEN** help, version, status, handoff, manifest, and service behavior have
  passed through the built executable
- **AND** the archive is bound to the release-owned manifest.

### Requirement: Coverage is strict and host-independent

The complete behavior suite SHALL keep aggregate, statement, branch, and every
semantic package coverage strictly greater than 95 percent. Required platform
branches SHALL be exercised through explicit semantic inputs rather than host
spoofing, exclusions, or CI-only production conditionals.

#### Scenario: A quality gate succeeds

- **WHEN** coverage is reported for the exact candidate tree
- **THEN** every required ratio is greater than 95 percent
- **AND** no required test is skipped merely because the quality host differs
  from the modeled platform.

### Requirement: Python structure limits are repository-owned

The repository quality owner SHALL measure production logical statements,
module effective lines, maximum function lines, and control-flow nesting. The
declared ceilings SHALL be positive, explicit, and exercised by contract tests;
normal source files SHALL receive no path-specific allowance above them.

#### Scenario: Structural policy drifts

- **WHEN** a ceiling is missing, non-positive, raised above the ratified bound,
  or bypassed for one production path
- **THEN** repository quality fails before the candidate is accepted.

#### Scenario: Production structure exceeds a ceiling

- **WHEN** a production module exceeds any declared structural dimension
- **THEN** the gate reports the exact path, measured value, and ceiling
- **AND** the implementation is simplified rather than compensated by another
  allowance.

### Requirement: Forge jobs are portable projections

Hosted jobs SHALL use supported native shells and filesystem semantics, install
their explicit operating-system prerequisites, and reach a terminal result on
an admitted project runner. A reused self-hosted checkout SHALL preserve Git
diagnostic integrity without changing runner-global configuration. A container
whose user does not own the GitHub checkout SHALL grant Git trust only to the
exact workflow workspace for the one archive command.

#### Scenario: Windows verifies the product

- **WHEN** the Windows matrix executes
- **THEN** it uses native PowerShell and Git index metadata for executable intent
- **AND** POSIX-only shell fixtures are excluded without disabling Windows
  product behavior.

#### Scenario: Linux builds an x86_64 asset on an ARM host

- **WHEN** the Docker executor runs on ARM
- **THEN** the release job explicitly selects an amd64 container
- **AND** packaging fails unless the container reports an x86_64-compatible
  machine.

#### Scenario: A required runner is unavailable

- **WHEN** Forge admission cannot match every job to an allowed runner
- **THEN** publication is blocked before a pipeline is treated as accepted
- **AND** a pending job is not reported as verification success.

#### Scenario: A GitHub release container reads the checked-out tag

- **WHEN** the Linux container user does not own `GITHUB_WORKSPACE`
- **THEN** the archive command trusts that exact workspace for that invocation
- **AND** no global, repository-local, system, or wildcard safe-directory rule
  is created
- **AND** the canonical `/workspace` source materialization continues.

### Requirement: Hosted product-tool execution uses the locked product environment

Hosted jobs SHALL install the product runtime and locked repository tooling
before executing dependency-bearing repository modules. Repository-only tools
and their tests SHALL run through the selected interpreter's import-safe module
entrypoint.

#### Scenario: Release metadata executes in GitLab

- **WHEN** the GitLab metadata job validates a branch or tag
- **THEN** it installs the complete environment from `uv.lock`
- **AND** the product CLI dependencies are importable.

#### Scenario: Repository quality executes in either Forge

- **WHEN** a hosted job invokes repository quality checks
- **THEN** it uses the package-aware module entrypoint
- **AND** release chronology tests receive complete tag history.

#### Scenario: GitHub resolves the supported Python matrix

- **WHEN** the GitHub verification workflow reads `.python-versions`
- **THEN** it first installs the locked quality environment
- **AND** it invokes the matrix owner through `python -m`
- **AND** no workflow-local parser duplicates the matrix semantics.

#### Scenario: GitLab executes repository release tests

- **WHEN** the GitLab metadata job runs repository-only tests under importlib mode
- **THEN** it invokes pytest through the selected interpreter
- **AND** repository `tools` modules remain importable without `PYTHONPATH`
  injection or a compatibility package.

### Requirement: Supply-chain pins are current and reproducible

Project metadata SHALL declare exact audited stable direct quality and packaging
dependencies, the committed uv lock SHALL own their transitive closure, hosted
Actions SHALL use immutable revisions, and GitLab Python images SHALL use
supported minor tags bound to immutable registry digests.

#### Scenario: A GitLab Python image is selected

- **WHEN** a GitLab job selects the supported floor or latest Python image
- **THEN** the reference contains the supported minor tag and a SHA-256 digest
- **AND** its minor version matches the corresponding boundary in
  `.python-versions`
- **AND** tests derive this relation instead of duplicating the concrete pin.

#### Scenario: The supply chain advances

- **WHEN** an audited stable dependency, hosted Action release, or CI base image
  supersedes the repository pin
- **THEN** its existing SSOT is updated without adding a parallel version owner
- **AND** lock, workflow, and repository quality contracts pass together.

#### Scenario: A stable transitive dependency advances

- **WHEN** the declared uv resolver selects a newer stable transitive dependency
- **THEN** the repository SHALL update only `uv.lock`
- **AND** a repeated resolution SHALL produce no further diff
- **AND** the complete locked verification graph SHALL pass before integration.

### Requirement: Hosted setup is deterministic and contention-free

GitHub workflows SHALL initialize Git explicitly, and concurrent Python matrix
jobs SHALL use distinct `setup-uv` cache identities.

#### Scenario: Hosted verification runs concurrently

- **WHEN** supported Python versions execute in parallel
- **THEN** each macOS matrix job uses its interpreter as the cache suffix
- **AND** Git resolves `main` without an initialization hint
- **AND** no verification, release, or provenance gate is weakened

### Requirement: Hosted fixtures are platform-default independent

Repository tests SHALL reach the intended Forge and signing behavior without
depending on a runner's Git default branch or text newline translation.

#### Scenario: Clone already has `main`

- **WHEN** a hosted Git configuration makes `main` the clone's current branch
- **THEN** the divergent-history fixture resets that branch to `origin/main`
- **AND** continues to test projection rejection rather than fixture setup

#### Scenario: Windows writes a temporary OpenSSH key

- **WHEN** release tests materialize an OpenSSH private key on Windows
- **THEN** the serialized key bytes are preserved exactly
- **AND** `ssh-keygen` can sign the checksum inventory

### Requirement: Terminal candidate integration is exact and local

A proven work lane SHALL advance the local candidate only through an explicit
compare-and-swap authority bound to the complete accumulated lane delta.

#### Scenario: The candidate remains the observed ancestor

- **WHEN** full proof passes for the clean archived work-lane HEAD
- **THEN** ETHOS SHALL move `candidate/dev` only from the previously observed ref
- **AND** any candidate, Lease, tree, or proof drift SHALL fail closed
- **AND** no remote Forge SHALL be queried or mutated.

### Requirement: Release signing uses one provider-owned key path

Release signing MUST use a complete caller-provided private-key file without
copying it. It MAY create one process-scoped private copy only to restore a
missing terminal newline on POSIX, and MUST leave Windows ACL ownership to the
secret provider. Tests MUST model these platform contracts independently.

#### Scenario: A Forge signs release assets

- **WHEN** GitHub or GitLab assembles one release asset set
- **THEN** the protected environment supplies an existing private-key path
- **AND** repository code preserves a complete key's path and security metadata
- **AND** OpenSSH signs and independently verifies the checksum inventory.

#### Scenario: The signing input is unsafe

- **WHEN** the path is absent, a symbolic link, or the trust input is empty
- **THEN** release assembly fails closed before publication.

#### Scenario: The provider supplies a complete key

- **WHEN** the private-key file ends with a terminal newline
- **THEN** OpenSSH receives that exact file path
- **AND** no temporary private-key copy is created.

#### Scenario: A POSIX file variable omits its terminal newline

- **WHEN** a valid POSIX private-key file lacks its terminal newline
- **THEN** signing uses one process-scoped `0600` normalized copy
- **AND** removes the copy after signing
- **AND** the success integration test runs only on POSIX.

#### Scenario: Windows input is incomplete

- **WHEN** a Windows private-key file lacks its terminal newline
- **THEN** the signer does not copy or rewrite the file
- **AND** OpenSSH rejects invalid input through the concise signing diagnostic
- **AND** the Windows regression proves fail-closed behavior rather than POSIX repair.

### Requirement: Native bundle containment uses filesystem identity

Release assembly MUST accept a resolved member inside the resolved bundle under
the host filesystem's canonical path identity, MUST reject external members,
and MUST exercise symlink behavior only on hosts that provide the modeled
filesystem semantics.

#### Scenario: Windows canonicalization rewrites separators

- **WHEN** Windows canonical path inputs compare through a host `commonpath`
- **THEN** the comparison result is normalized before identity comparison
- **AND** an internal case-variant member remains accepted

#### Scenario: Windows returns a case-variant path spelling

- **WHEN** an internal resolved member differs from the bundle path only by case
- **THEN** release assembly accepts the member
- **AND** retains its logical bundle path

#### Scenario: A symlink resolves outside the bundle

- **WHEN** a member resolves outside the canonical bundle boundary
- **THEN** release assembly fails closed
- **AND** publishes no asset from that invocation

#### Scenario: A POSIX bundle contains internal symlinks

- **WHEN** the host supports the modeled POSIX symlink semantics
- **THEN** release assembly materializes internal links
- **AND** rejects links that resolve outside the bundle

### Requirement: Native handoff fixtures release temporary bundles

Native release acceptance MUST terminate and re-observe every fixture-owned
proxy process before removing its copied bundle, MUST tolerate only a transient
Windows mapped-module lock for a bounded interval, and MUST fail if the payload
remains locked.

#### Scenario: Windows releases a mapped module after process exit

- **WHEN** every fixture-owned proxy process has exited
- **AND** the first payload cleanup reports `PermissionError`
- **THEN** acceptance retries cleanup within a bounded deadline
- **AND** succeeds when the lock is released

#### Scenario: The payload remains locked

- **WHEN** cleanup continues to report `PermissionError` through the deadline
- **THEN** acceptance fails
- **AND** does not hide the residual payload

#### Scenario: Cleanup reports another error

- **WHEN** payload cleanup reports an error other than `PermissionError`
- **THEN** acceptance fails immediately

### Requirement: Quality policy has explicit owners

The repository SHALL keep tool-native and repository-level quality policy in
one explicit owner per concern, while ETHOS registers executable gates.

#### Scenario: A quality gate is planned

- **WHEN** ETHOS plans or executes the Proxy quality proof
- **THEN** its Nox command consumes the tracked policy owners
- **AND** `pyproject.toml` does not duplicate lint, test, type, coverage, or
  repository-structure policy.

### Requirement: Commit semantics are machine checked

The repository SHALL admit human commit subjects only through one scoped
Conventional Commit grammar and SHALL classify generated lifecycle commits
through explicit semantic patterns.

#### Scenario: A human commit omits its semantic scope

- **WHEN** repository quality validates its subject
- **THEN** the commit is rejected before publication.

### Requirement: A patch release has one source identity and independent Forge projections

The exact patch identity MUST come from tracked `VERSION`. Its package,
Changelog, documentation, signed tag, and assets MUST derive from one accepted
source commit. GitLab and GitHub MUST each complete their own signed publication
without querying, mutating, or depending on the other Forge.

#### Scenario: Both Forge planes publish the current patch

- **WHEN** local exact-HEAD proof passes for the value in `VERSION`
- **THEN** GitLab and GitHub each publish the corresponding signed tag and complete native asset set from that same source commit
- **AND** a read-only audit proves source and asset consistency after both publications complete.

#### Scenario: One Forge publication fails

- **WHEN** either Forge cannot publish the current patch
- **THEN** the other Forge remains independently publishable and usable
- **AND** no existing tag, run, Release, or asset is rewritten to hide failure.

#### Scenario: A release asset is installed

- **WHEN** an operator installs the platform archive for the value in `VERSION`
- **THEN** the installer verifies the complete release set and external trust anchor before mutation
- **AND** the installed executable reports that exact version and passes runtime acceptance.

### Requirement: Commit grammar follows the checkout's available integration boundary

Commit-subject verification MUST validate the change range after the most local
available integration boundary without requiring local governance refs in a
Forge checkout.

#### Scenario: A Work Lane has a candidate boundary

- **WHEN** `candidate/dev` is available
- **THEN** only commits after that candidate boundary are checked
- **AND** an invalid Work Lane subject is rejected.

#### Scenario: A Forge tag checkout has no candidate ref

- **WHEN** the checkout exposes `origin/dev` or `origin/main` but no `candidate/dev`
- **THEN** the available remote integration ref is used as the boundary
- **AND** an invalid subject after that boundary is rejected
- **AND** no candidate or Work Lane ref is published to satisfy the checker.

#### Scenario: No integration boundary is available

- **WHEN** the repository has Git history but none of the declared integration refs
- **THEN** all available history is checked
- **AND** history unavailability remains a fail-closed diagnostic.

### Requirement: Hosted fixtures own deterministic repository and process identities

Hosted verification MUST create Git repositories with an explicit non-product
initial branch. Native handoff fixtures MUST capture every successor process
generation proven through expected health identity and MUST confirm those exact
generations have exited before their executable payload is removed.

#### Scenario: Host Git configuration differs

- **WHEN** a quality fixture creates an isolated repository
- **THEN** its initial branch is independent of the host's Git defaults
- **AND** no product integration ref is created implicitly.

#### Scenario: Captured process later denies argv access

- **WHEN** expected health proves a native successor and captures its PID,
  executable, and creation time
- **AND** a later argv lookup is unavailable during process exit
- **THEN** teardown terminates the captured PID generation without relying on
  that later argv lookup
- **AND** payload deletion starts only after the generation is absent.

#### Scenario: A captured PID is reused

- **WHEN** the current process creation time differs from the captured value
- **THEN** teardown treats the captured generation as absent
- **AND** does not signal the new process.

#### Scenario: Process inventory omits a serving successor

- **WHEN** a native handoff fixture has captured the successor at bound health
- **THEN** teardown still terminates that exact generation
- **AND** inventory remains only a secondary discovery path.

### Requirement: Publication topology has one declared peer collection

The repository SHALL declare local verification and installation once and
represent every remote publication plane as one peer in the same collection.
Forge-specific scalar aliases SHALL NOT be accepted as parallel configuration
owners.

#### Scenario: GitLab and GitHub are both available

- **WHEN** publication readiness compiles the repository release declaration
- **THEN** GitLab and GitHub appear as independent peers with their own Git remote and CI surface
- **AND** neither peer supplies credentials, jobs, tags, Releases, or assets for the other.

#### Scenario: A retired scalar field returns

- **WHEN** the publication table contains a Forge-specific remote or CI scalar
- **THEN** repository quality rejects the declaration
- **AND** no compatibility reader or inferred default peer is used.

### Requirement: Forge release projections use one exact common runtime

The repository SHALL define one immutable runtime identity for every native
asset built on more than one Forge, while each Forge remains an independent
builder and publisher.

#### Scenario: Independent Linux builders select the release runtime

- **WHEN** GitLab and GitHub build the Linux release asset
- **THEN** both use the repository-owned image digest and architecture
- **AND** both materialize the release commit at the same canonical build root
- **AND** neither builder consumes artifacts or state from the other Forge

### Requirement: Native release payloads are reproducible

Native release payloads SHALL contain only runtime-required bytes and portable
metadata.

#### Scenario: Equivalent source is built from distinct checkout roots

- **WHEN** the same release commit is built twice in the declared runtime
- **THEN** the resulting common-platform archives are byte-identical
- **AND** no checkout path, installer timestamp, or runner-private metadata is present

#### Scenario: A builder drifts from the declared runtime

- **WHEN** a build uses a different image, Python patch release, or toolchain
- **THEN** release verification fails before publication

### Requirement: Hosted native asset jobs preserve path identity

A hosted native asset job SHALL write each accepted platform bundle to the exact directory consumed by its artifact uploader across every process, container, and host boundary.

#### Scenario: Linux build runs in a job container

- **WHEN** the pinned Linux release container builds and accepts the native asset
- **THEN** the output directory is mounted into both the container and host action
- **AND** the upload action reads that exact directory without path translation
- **AND** GitLab and GitHub continue to build and publish independently

### Requirement: Container and action paths share one mounted workspace

The GitHub Linux release job SHALL write its output through the container's
runtime `GITHUB_WORKSPACE` path. The upload action SHALL read the equivalent
`${{ github.workspace }}` path.

#### Scenario: Linux native asset crosses the container boundary

- **WHEN** the tagged Linux job builds the native release asset
- **THEN** the container writes below `$GITHUB_WORKSPACE/.release-assets`
- **AND** the upload action reads `${{ github.workspace }}/.release-assets`
