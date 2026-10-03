# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/). It preserves all released,
user-visible changes. GitLab and GitHub keep independent signed tags and
Releases for the same product versions; neither Forge is the other's publication
authority. Version headings stay on this page; explicit history links name the
peer they open.

## Unreleased

History: [GitLab][Unreleased-gitlab] · [GitHub][Unreleased-github]

### Changed

- Use native TOML for pytest and Coverage configuration, preserving direct test
  discovery, warning policy, and explicit coverage scope without parallel INI
  files.

### Fixed

- Bind promotion to the exact accepted source object, not an equal tree or a
  branch name. Run the declared GitLab native tag checks after tag identity and
  signature verification without repeating native construction on `main`.
- Check online references on the selected publication plane without requiring
  access to the other declared repository. Broken selected, public, and local
  links still fail; an excluded peer is not reported as available.
- Stop and verify an interrupted first installation's native service and
  processes before recovery discards its payload or journal. An unavailable
  health response no longer permits false rollback success with a service left
  behind; uncertain cleanup preserves recovery authority.
- Verify selector, rollback snapshot, and command ownership before stopping a
  recovery candidate. Missing native identity permits removal only after proved
  service absence; failed Windows task queries no longer stand for absence.
- Refresh the official OpenSpec dependency to stable 1.14.0, retaining the
  existing Change, strict native validation, and dependency closure.
- Refresh locked native Vale to stable 3.24.0 and test the existing prose rule
  with its native coverage check, so a rule that never fires cannot pass.
- Run Python-only CI proof and release-asset binding with GitHub's native Python
  shell, avoiding a Bash input deadlock while preserving required-job refusal
  and exact current/predecessor selection.
- Keep version headings on this page and offer each Forge's own history links;
  bind release navigation to the declared repository rather than Git transport.
- Preserve the initial installation failure when native cleanup or payload
  rollback also fails, and report numeric generation-removal errors without
  exposing private paths.
- Run the macOS watchdog in the native user Background domain without requiring
  a graphical login; verify legacy GUI service removal and preserve unrelated
  registrations, disabled-state overrides and launch-agent files.
- Observe registered macOS services even when their plist is missing, and reject
  ambiguous domain observations before reporting lifecycle success.
- Reject unowned or symbolic-link macOS launch-agent carriers before service
  mutation; write accepted carriers atomically and preserve changed
  replacements.
- Reject reload results without distinct positive process IDs and cleanup
  results with invalid process counts instead of reporting false success.
- Stop the full verification graph at its first failed prerequisite instead of
  running dependent expensive checks after admission has already failed.
- Give isolated signing tests their own short native agent socket and bounded
  process teardown, preserving cold development checks under deeply nested
  homes.

## 4.0.5 - 2026-09-23

History: [GitLab][4.0.5-gitlab] · [GitHub][4.0.5-github]

### Changed

- Bind `VERSION`, local product tags, and this Changelog as one release
  identity; enforce Keep a Changelog structure and fold unpublished historical
  headings into the releases that actually carried their changes.

### Fixed

- Preserve current-turn tool catalogs and compaction controls during Responses
  projection and recovery, restoring Codex tool invocation through the Proxy.
- Preserve encrypted delegated task bodies when an upstream rejects ciphertext;
  do not retry with a header-only task.
- Reject incomplete lifecycle results instead of presenting false success, and
  keep native failure diagnostics free of private host details.

## 4.0.4 - 2026-09-19

History: [GitLab][4.0.4-gitlab] · [GitHub][4.0.4-github]

### Changed

- Refresh the locked Python, Node, uv, OpenSpec, formatting, linting, packaging,
  CI action, and container-image dependency graph to the latest compatible
  stable releases verified by the repository supply-chain checks.
- Bind product, quality, configuration, and release responsibilities to their
  canonical semantic owners, removing duplicated repository policy carriers.

### Fixed

- Observe the terminal process state after bounded lifecycle waits, preventing a
  completed child from being reported as still running.
- Verify published native release assets on macOS, Linux, and Windows through
  the shared release lifecycle contract.

## 4.0.3 - 2026-09-18

History: [GitLab][4.0.3-gitlab] · [GitHub][4.0.3-github]

### Fixed

- Retire the watchdog and prewarm processes owned by an obsolete payload
  generation before deleting its files. Windows purge and upgrade no longer fail
  when those processes retain native modules from the retired generation.
- Bind commit admission to the exact Forge event object and keep the commit
  policy in its declared ETHOS profile instead of a duplicate repository file.

## 4.0.2 - 2026-09-16

History: [GitLab][4.0.2-gitlab] · [GitHub][4.0.2-github]

### Fixed

- Preserve named asynchronous tool deliveries after an initial result. Keep each
  later result in its original position with explicit tool attribution, rather
  than rejecting valid continuing conversations as duplicate output.
- Share delivery admission across replay projection, diagnostics and bounded
  recovery while retaining rejection of repeated identities and mismatched
  calls.
- Preserve encrypted agent-task bodies and native envelopes instead of sending
  only their visible routing headers. Reject malformed ciphertext and prevent
  shrinking recovery from dropping required agent-control input.

## 4.0.1 - 2026-09-15

History: [GitLab][4.0.1-gitlab] · [GitHub][4.0.1-github]

### Fixed

- Forward available SSE events without waiting for an application buffer to
  fill. Finish each HTTP response at its terminal event even when the upstream
  leaves its connection open.
- Release upstream connections when downstream writes fail. Preserve an
  interrupted committed stream as truncated HTTP instead of appending another
  status line or a successful chunk terminator; never replay delivered output.
- Isolate concurrent CI dependency-cache writers and refresh stable repository
  tooling dependencies without changing the supported Python range.

## 4.0.0 - 2026-09-15

History: [GitLab][4.0.0-gitlab] · [GitHub][4.0.0-github]

### Changed

- Require durable generation-based installations for in-place upgrades. Older
  flat installations must be explicitly uninstalled before a fresh install;
  their removed migration path is the breaking change in this release.
- Keep installation, rollback, recovery and purge on one transaction owner;
  retain interrupted cleanup authority until exact owned resources are retired.
- Require a reachable Linux user service manager without changing the host's
  lingering policy or leaving a fallback service behind.

### Fixed

- Recover output-free upstream `server_error` streams within the existing
  reconnect deadline. SSE comments, heartbeats, `[DONE]` and JSON whitespace no
  longer prematurely commit a retry-safe response. Already-delivered output,
  tool calls, permanent failures and unknown failures are never replayed.
- Report bounded stream failure classes and request identifiers without logging
  upstream messages or caller payloads.
- Preserve exact active installations and restore prior generation projections
  through interrupted lifecycle transitions.
- Validate publication, native asset and quality-policy identities strictly;
  verify product, tooling and orchestration coverage independently.

## 3.1.17 - 2026-09-12

History: [GitLab][3.1.17-gitlab] · [GitHub][3.1.17-github]

### Fixed

- Preserve inline PNG, JPEG, WebP, and GIF image data URLs through Responses
  replay and classified retries without changing image bytes, detail, or order.
  Image-only dialogue and paired tool results remain available to the model.

## 3.1.16 - 2026-09-05

History: [GitLab][3.1.16-gitlab] · [GitHub][3.1.16-github]

### Fixed

- Preserve request admission during capability-qualified upgrade and rollback
  handoff, so new and in-flight Responses requests are not rejected with
  `proxy_draining`; retain bounded draining only for legacy native-generation
  replacement.

## 3.1.15 - 2026-09-04

History: [GitLab][3.1.15-gitlab] · [GitHub][3.1.15-github]

### Fixed

- Omit the exact non-semantic empty assistant placeholder emitted by Codex
  during replay while preserving subsequent portable history and continuing to
  reject every other empty or unproved dialogue shape.

## 3.1.14 - 2026-09-02

History: [GitLab][3.1.14-gitlab] · [GitHub][3.1.14-github]

### Fixed

- Bind rollback to an explicit target release, return an idempotent no-op when
  that release is already proven active, and reject unrelated targets before
  lifecycle mutation.
- Close an interrupted, unselected reverse transaction after proving the
  selected installation, command, immutable payload, and accepting runtime are
  unchanged, without requiring a restoration snapshot that was never needed.

## 3.1.13 - 2026-09-02

History: [GitLab][3.1.13-gitlab] · [GitHub][3.1.13-github]

### Fixed

- Reject malformed, unsupported, or incomplete Codex local-shell replay before
  upstream dispatch while removing valid complete call/output pairs without
  disturbing the current dialogue.

## 3.1.12 - 2026-09-01

History: [GitLab][3.1.12-gitlab] · [GitHub][3.1.12-github]

### Changed

- Use one Ruff configuration for source and docstring policy instead of a
  parallel docstring-only configuration.

### Fixed

- Classify Responses input items through one authority so valid Codex-local
  shell call/output history is removed as a complete pair while current dialogue
  continues, and report recognized unsupported items as schema drift rather than
  unknown input.

## 3.1.11 - 2026-08-31

History: [GitLab][3.1.11-gitlab] · [GitHub][3.1.11-github]

### Fixed

- Make GitLab publication retries reuse byte-identical generic-package assets
  instead of creating duplicate file records, and retain bounded provider
  response details when the API rejects a request.

## 3.1.10 - 2026-08-31

History: [GitLab][3.1.10-gitlab] · [GitHub][3.1.10-github]

### Fixed

- Preserve the caller's active branch, HEAD, index, and worktree while verifying
  an annotated release tag against its expected commit.

## 3.1.9 - 2026-08-31

History: [GitLab][3.1.9-gitlab] · [GitHub][3.1.9-github]

### Fixed

- Accept Codex 0.151.0 function-call outputs carrying documented namespace
  metadata, while keeping that metadata outside the provider-portable outbound
  pair and continuing to reject unproved output fields.

## 3.1.8 - 2026-08-31

History: [GitLab][3.1.8-gitlab] · [GitHub][3.1.8-github]

### Fixed

- Replay bounded standalone cross-task tool deliveries as deterministic
  provider-neutral assistant messages without inventing call identities or
  modifying conversation history.

## 3.1.7 - 2026-08-30

History: [GitLab][3.1.7-gitlab] · [GitHub][3.1.7-github]

### Changed

- Remove obsolete root and archived-change Commitment carriers now that official
  OpenSpec artifacts are the sole repository intent source.

### Fixed

- Isolate native handoff diagnostics so lifecycle tests cannot leak logs into
  the repository or another test's state.
- Correct macOS launchd override guidance without introducing unsafe domain-wide
  cleanup behavior.

## 3.1.6 - 2026-08-29

History: [GitLab][3.1.6-gitlab] · [GitHub][3.1.6-github]

### Changed

- Refresh the locked Python and Node development toolchains to their current
  stable releases while preserving deterministic, attested installation.
- Define one strict branch-role policy for work, proposal, candidate, accepted,
  and release refs across local, GitLab, and GitHub workflows.

## 3.1.5 - 2026-08-29

History: [GitLab][3.1.5-gitlab] · [GitHub][3.1.5-github]

### Changed

- Remove unconsumed OpenSpec summary, scope, capability, and index carriers so
  the official OpenSpec artifacts remain the sole repository intent model.

### Fixed

- Make published-predecessor downloads shell-independent so the same release
  compatibility path runs on macOS, Linux, and Windows.

## 3.1.4 - 2026-08-28

History: [GitLab][3.1.4-gitlab] · [GitHub][3.1.4-github]

### Fixed

- Make `uninstall --purge` preserve and report unverified control-root residue
  instead of claiming complete removal, and reject a later installation before
  it can create an invalid predecessor-free transaction.

## 3.1.3 - 2026-08-28

History: [GitLab][3.1.3-gitlab] · [GitHub][3.1.3-github]

### Fixed

- Keep the installed lifecycle command on the newest verified selected release
  when the serving payload rolls back, so PATH-based status, diagnosis,
  recovery, reversal, uninstall, and future upgrade admission remain current.

## 3.1.2 - 2026-08-26

History: [GitLab][3.1.2-gitlab] · [GitHub][3.1.2-github]

### Fixed

- Complete native handoff by proving the exact predecessor process generation
  has exited and the finalized successor generation remains healthy, rather than
  waiting for platform-specific TCP-owner attribution to move.
- Use the same portable completion proof for reload, upgrade, rollback, and
  controller-failure resolution.

## 3.1.1 - 2026-08-26

History: [GitLab][3.1.1-gitlab] · [GitHub][3.1.1-github]

### Fixed

- Require rollback to prove that the finalized predecessor PID is the sole
  verified product listener before reporting success, eliminating the transient
  false-success interval while the displaced generation drains.

## 3.1.0 - 2026-08-25

History: [GitLab][3.1.0-gitlab] · [GitHub][3.1.0-github]

### Added

- Add explicit one-step rollback to the sole verified predecessor retained by
  the last successful upgrade, using the existing transaction, native-service,
  handoff, and runtime-identity owners.

### Changed

- Make retained-generation promotion one idempotent finalization transition:
  verify, materialize, atomically select, clean superseded generations, and
  resume safely after interruption at either filesystem boundary.
- Keep rollback and recovery semantically distinct, and project retained state
  as transaction-owned while an installation transaction is active.

## 3.0.5 - 2026-08-25

History: [GitLab][3.0.5-gitlab] · [GitHub][3.0.5-github]

### Fixed

- Distinguish missing, malformed, and incomplete payload transaction journals,
  so `recover` reports the exact unavailable recovery authority instead of one
  ambiguous failure.
- Preserve rollback and recovery authority across native lifecycle transitions.
- Make native lifecycle teardown own the exact temporary service, process set,
  and macOS launch-agent path, preventing test services from leaking into the
  host while preserving the installed service.

## 3.0.4 - 2026-08-24

History: [GitLab][3.0.4-gitlab] · [GitHub][3.0.4-github]

### Fixed

- Preserve each GitLab publication credential kind exactly, using the matching
  environment variable and HTTP header without guessing or fallback.
- Compose validated GitHub and GitLab job evidence through one provider-neutral
  publication schema so byte-identical releases can be proved without parallel
  evaluator shapes.
- Prove native macOS lifecycle tests leave no new product-owned launchd
  registration, override, process, or plist residue while preserving the
  installed service.

## 3.0.3 - 2026-08-24

History: [GitLab][3.0.3-gitlab] · [GitHub][3.0.3-github]

### Fixed

- Remove empty directory residue nested below files retired from the verified
  predecessor payload while preserving every unowned file and symlink.

## 3.0.2 - 2026-08-23

History: [GitLab][3.0.2-gitlab] · [GitHub][3.0.2-github]

### Fixed

- Prove the installed native service lifecycle on macOS, Linux, and Windows,
  including exact teardown after interrupted validation without touching the
  canonical service.
- Build Linux release bytes in the pinned container and validate the resulting
  executable against a real user systemd manager on a native Linux runner.
- Derive the supported release-platform inventory from one product identity
  authority and remove the redundant runtime dependency used only for home
  directory discovery.

## 3.0.1 - 2026-08-23

History: [GitLab][3.0.1-gitlab] · [GitHub][3.0.1-github]

### Fixed

- Decouple native payload prewarm from public CLI syntax through one private,
  version-neutral executable role, preventing future command cleanup from
  breaking transactional upgrades.
- Document the one-time verified-successor bootstrap required when upgrading
  directly from a 2.x installer that predates the stable private protocol.

## 3.0.0 - 2026-08-23

History: [GitLab][3.0.0-gitlab] · [GitHub][3.0.0-github]

### Changed

- Expose release identity through the conventional top-level `--version` option
  and remove the redundant `version` subcommand.

## 2.0.58 - 2026-08-22

History: [GitLab][2.0.58-gitlab] · [GitHub][2.0.58-github]

### Fixed

- Keep the native runtime carrier stable across supported installer generations,
  so the published predecessor can start and hand off to its signed successor
  without a schema migration layer.
- Keep exact macOS launch-agent ownership in the live installation context
  rather than persisting a host-only home path in the product runtime carrier.
- Resume supported upgrades from `2.0.56`; `2.0.57` is an unusable intermediate
  release and is not an upgrade predecessor.

## 2.0.57 - 2026-08-22

History: [GitLab][2.0.57-gitlab] · [GitHub][2.0.57-github]

### Changed

- Generate the GitHub and GitLab verification graphs from one CUE definition,
  with separately observable source, quality, Python 3.12–3.14, performance,
  native-platform, promotion, and release responsibilities.
- Strengthen the repository quality contract for formatting, types, docstrings,
  dependencies, dead code, naming, documentation, links, secrets, architecture,
  coverage, and repository hygiene without warning suppressions.
- Add measured latency, throughput, startup, handoff, status, streaming, and
  large-payload memory budgets using the locked `pyperf` toolchain.
- Build one provider-neutral signed release bundle for independent byte-exact
  publication and verification by GitHub and GitLab.
- Provision the repository-owned projection toolchain in release-tag governance
  so a clean hosted runner can verify the generated Forge workflows.
- Require current upgrades to begin from the canonical installed executable;
  remove the consumed alternate-launcher migration bridge and its parallel
  handoff authority.

### Fixed

- Bind macOS test services to their exact launchd target and teardown owner so
  native lifecycle tests cannot leave temporary background services or touch the
  installed production listener.

## 2.0.56 - 2026-08-21

History: [GitLab][2.0.56-gitlab] · [GitHub][2.0.56-github]

### Changed

- Require every private service role to read the executable-owned
  `runtime-config.json`; the temporary `2.0.52 → 2.0.55` carrier bridge has
  completed its migration and is no longer part of the product.
- Define native forward-upgrade support through the immediately preceding
  released runtime instead of retaining historical fallback behavior.

## 2.0.55 - 2026-08-21

History: [GitLab][2.0.55-gitlab] · [GitHub][2.0.55-github]

### Fixed

- Let the successor handoff child materialize the sole `runtime-config.json`
  carrier when an admitted published predecessor predates that carrier, while
  rejecting partial predecessor settings and keeping every other private role
  fail-closed.
- Drive published-predecessor compatibility with the predecessor executable that
  users actually invoke, preventing candidate-driven false-positive upgrade
  proof.

## 2.0.54 - 2026-08-21

History: [GitLab][2.0.54-gitlab] · [GitHub][2.0.54-github]

### Fixed

- Keep exact-successor health observation bounded across failed reads during
  native listener handoff, so a proven successor is not rolled back while
  ownership is transferring.

## 2.0.53 - 2026-08-20

History: [GitLab][2.0.53-gitlab] · [GitHub][2.0.53-github]

### Fixed

- Move native-supervisor rebinding from the handoff child into the installer
  transaction before listener transfer, so Linux and Windows successors do not
  terminate or replace the process that is actively finalizing the handoff.
- Replace the macOS watchdog by exact launchd service generation, proving the
  predecessor process exited and the successor executes the committed payload
  without interrupting the independent listener.
- Make `runtime-config.json` the sole secret-free runtime carrier used by the
  product, watchdog, and native-service projections; remove duplicated platform
  configuration state.
- Bind native service inspection and teardown to the exact executable, service
  label, and platform registration target so isolated lifecycle tests cannot
  leak persistent host services or touch the canonical installation.
- Project the same supervision contract through launchd, systemd user services,
  and Windows Task Scheduler while retaining native platform registration and
  diagnostics.

## 2.0.52 - 2026-08-20

History: [GitLab][2.0.52-gitlab] · [GitHub][2.0.52-github]

### Fixed

- Restart native supervision from the committed release before listener handoff,
  restore predecessor supervision after rollback, and reap watchdog-owned
  listener children so upgrades leave no stale supervisor generation or zombie
  process.

## 2.0.51 - 2026-08-20

History: [GitLab][2.0.51-gitlab] · [GitHub][2.0.51-github]

### Fixed

- Retire files owned only by the verified predecessor payload while preserving
  unknown installation content and restoring the complete prior projection on
  rollback.
- Finalize an upgrade only after the shared listener reports the exact successor
  process and payload identity; record a concise, secret-safe failure phase when
  convergence fails.
- Isolate frozen-executable prewarm from inherited Python runtime variables.
- Exercise a real signed predecessor release through fresh installation,
  concurrent request and SSE handoff, reload, purge, and transaction cleanup.

## 2.0.50 - 2026-08-19

History: [GitLab][2.0.50-gitlab] · [GitHub][2.0.50-github]

### Fixed

- Recover canonical empty prepared installation transactions while preserving
  ambiguous or mutated residue for explicit diagnosis.
- Reconcile an install-owned alternate launcher into the canonical native
  executable through a retry-safe protocol-v2 handoff without interrupting an
  active response.
- Bind alternate native services to their selected payload and state roots, and
  verify a handoff child by its canonical kernel executable when the process
  argument still names the retiring bridge.
- Read handoff release identity from the verified payload manifest instead of a
  stale installation-root version file.
- Make every public command's help, parameter validation, human output, JSON
  output, next action, and exit status explicit and consistent in the native
  product interface.
- Preserve the Windows system root in the otherwise isolated native command test
  environment, so the packaged executable can load side-by-side system
  assemblies while still proving that it does not require Python on `PATH`.
- Keep human CLI output encodable by the default Windows console code page while
  retaining the same aligned, scannable result model.

## 2.0.47 - 2026-08-19

History: [GitLab][2.0.47-gitlab] · [GitHub][2.0.47-github]

### Fixed

- Align GitLab tag verification with the provider-neutral three-argument CLI
  contract, removing the retired Forge positional token that blocked the
  `v2.0.46` tag pipeline.

## 2.0.46 - 2026-08-19

History: [GitLab][2.0.46-gitlab] · [GitHub][2.0.46-github]

### Fixed

- Validate ordinary and published source checkouts with release-state-aware
  metadata tests instead of invoking the pre-tag preparation contract after a
  release tag already exists.

## 2.0.45 - 2026-08-19

History: [GitLab][2.0.45-gitlab] · [GitHub][2.0.45-github]

### Fixed

- Pin every native release asset to Python 3.14.7 and reject platform-specific
  interpreter drift before packaging.
- Build outbound TLS contexts from the packaged Mozilla CA trust store instead
  of relying on host-dependent certificate discovery.
- Preserve secret-safe transport diagnostics for exception class, errno, and TLS
  verification code without recording upstream messages or request data.
- Derive native supervision identity from alternate installation roots so
  isolated validation cannot unload or replace the canonical service.

## 2.0.44 - 2026-08-18

History: [GitLab][2.0.44-gitlab] · [GitHub][2.0.44-github]

### Changed

- Refresh the locked runtime and release toolchain to current stable versions.
- Keep provider-native GitLab and GitHub publication independent.

## 2.0.43 - 2026-08-17

History: [GitLab][2.0.43-gitlab] · [GitHub][2.0.43-github]

### Changed

- Refresh the complete locked Python dependency graph to current stable
  releases.
- Use `origin` as the sole GitLab remote authority and remove the redundant
  release-only alias.

## 2.0.42 - 2026-08-17

History: [GitLab][2.0.42-gitlab] · [GitHub][2.0.42-github]

### Changed

- Remove the obsolete Claims, Chronicle, and repository `evidence/` authority;
  current product source, specifications, tests, and Forge-native records now
  retain their own evidence without a parallel taxonomy.
- Align documentation and decision-record names with their semantic owners,
  removing ambiguous directory indexes and redundant repository checks.

## 2.0.41 - 2026-08-17

History: [GitLab][2.0.41-gitlab] · [GitHub][2.0.41-github]

### Fixed

- Bind each Forge audit to the projection receipt for its exact provider tip, so
  provenance continuity is explicit and stale or drifting coordinates fail
  closed.
- Derive audited branch roles from repository policy and fetch release tags in
  one bounded operation, removing false residue reports and avoidable latency.

## 2.0.40 - 2026-08-16

History: [GitLab][2.0.40-gitlab] · [GitHub][2.0.40-github]

### Changed

- Replace heuristic quality checks with positive, risk-backed repository
  contracts.
- Clarify provider admission, authority boundaries, and repository information
  architecture.
- Update the locked development toolchain.

## 2.0.39 - 2026-08-16

History: [GitLab][2.0.39-gitlab] · [GitHub][2.0.39-github]

### Fixed

- Make independent Linux native builds byte-identical by collecting `ctypes`
  through PyInstaller's supported source-module mode.
- Prewarm the exact committed successor executable and honor the configured
  installation deadline during transactional handoff.

## 2.0.38 - 2026-08-15

History: [GitLab][2.0.38-gitlab] · [GitHub][2.0.38-github]

### Fixed

- Verify the native user-command projection by exact file identity on Windows,
  where the product uses a hard link, while retaining exact symbolic-link
  assertions on macOS and Linux.
- Build lifecycle status fixtures from host-native absolute paths so the Windows
  matrix tests installed-state validation instead of POSIX syntax.

## 2.0.37 - 2026-08-15

History: [GitLab][2.0.37-gitlab] · [GitHub][2.0.37-github]

### Added

- Project the verified native executable into the current user's platform
  command directory as part of the payload transaction, without wrappers or
  shell-profile changes.
- Report command discoverability in `status` and `doctor` from the same
  installed-state authority used by upgrade and uninstall.

### Fixed

- Read the installed release from canonical installed state instead of a
  nonexistent `VERSION` file inside the installed payload.
- Roll back and uninstall only the exact command link owned by the installed
  payload, including when the invoking shell's environment has changed.

## 2.0.36 - 2026-08-15

History: [GitLab][2.0.36-gitlab] · [GitHub][2.0.36-github]

### Fixed

- Install the locked project runtime together with the quality tool group in
  GitLab publication jobs, so repository release commands can import their
  declared Cyclopts dependency.
- Preserve GitLab and GitHub as independent publication planes; the forward
  patch does not change proxy runtime behavior or provider configuration.

## 2.0.35 - 2026-08-15

History: [GitLab][2.0.35-gitlab] · [GitHub][2.0.35-github]

### Fixed

- Publish GitLab releases from the immutable repository runtime without mutable
  operating-system package installation.
- Preserve the failed GitLab 2.0.34 release while GitLab and GitHub publish the
  forward patch independently.

## 2.0.34 - 2026-08-14

History: [GitLab][2.0.34-gitlab] · [GitHub][2.0.34-github]

### Fixed

- Keep every GitLab post-sync command on the Python environment selected by uv,
  and cache UV-managed compatibility runtimes by target platform.

## 2.0.33 - 2026-08-14

History: [GitLab][2.0.33-gitlab] · [GitHub][2.0.33-github]

### Fixed

- Restore failed native upgrades exactly by removing bundle members introduced
  only by the rejected candidate.

## 2.0.32 - 2026-08-14

History: [GitLab][2.0.32-gitlab] · [GitHub][2.0.32-github]

### Fixed

- Verify the selected native archive and platform manifest as members of the
  complete signed multi-platform checksum manifest. Formal releases no longer
  fail installation merely because the manifest also contains other platforms.

## 2.0.31 - 2026-08-11

History: [GitLab][2.0.31-gitlab] · [GitHub][2.0.31-github]

### Fixed

- Remove installer-local metadata before native executable freezing so common
  platform assets built independently by GitLab and GitHub are byte-identical.

## 2.0.30 - 2026-08-11

History: [GitLab][2.0.30-gitlab] · [GitHub][2.0.30-github]

### Fixed

- Write the GitHub Linux asset through the container's runtime workspace path
  while the host-side upload action reads the equivalent workspace expression.

## 2.0.29 - 2026-08-11

History: [GitLab][2.0.29-gitlab] · [GitHub][2.0.29-github]

### Fixed

- Publish the Linux native asset from a workspace path shared by the GitHub job
  container and host-side artifact uploader.
- Treat an exact-generation Linux zombie retained by a non-reaping container
  parent as exited after handoff teardown, while preserving PID-reuse and
  inaccessible-process safeguards.
- Trust only the exact GitHub Actions workspace while the Linux release
  container archives the checked-out release commit.
- Build the common Linux asset in one immutable runtime on both independent
  Forges.
- Materialize the release commit at the same canonical build root on both
  Forges.
- Remove checkout paths and installer timestamps from native release payloads.
- Refresh Hatchling and Nox to their latest stable releases.

## 2.0.25 - 2026-08-11

History: [GitLab][2.0.25-gitlab] · [GitHub][2.0.25-github]

### Fixed

- Preserve the active virtual-environment interpreter during hosted GitHub
  release validation.
- Normalize ephemeral release signing keys so GitLab file variables without a
  terminal newline remain valid OpenSSH inputs.
- Preserve complete provider-owned signing-key files so Windows OpenSSH retains
  their secure ACLs.

## 2.0.24 - 2026-08-11

History: [GitLab][2.0.24-gitlab] · [GitHub][2.0.24-github]

### Changed

- Publish the accepted terminal reliability contract as an independent,
  provider-native release on GitLab and GitHub.
- Keep release identity, installation, and runtime acceptance bound to one
  verified source tree while preserving the failed v2.0.23 records.
- Replace the repeatedly extracted one-file executable with one complete,
  manifest-bound native bundle. Installation prewarms the staged bundle before
  payload mutation, and handoff, rollback, recovery, purge, and signed assets
  now share its exact recursive inventory.
- Install a fresh payload or hand off from one verified current-native runtime;
  reject every incompatible installation before mutation.
- Keep one manifest-owned rollback and recovery model. Remove version-specific
  inventories, interpreter entrypoints, migration paths, and bypass switches.
- Keep specifications, tests, documentation, and the executable on the same
  provider-portable runtime contract.
- Present human CLI status, diagnosis, installation, reload, and uninstall
  results as concise aligned pages while retaining the stable JSON interface.
- Require statement and branch coverage above 95 percent for every semantic
  runtime package, and keep successful Git admission hooks silent.
- Remove proxy-owned ordinary-request concurrency ceilings, provider-route
  queues, and route serialization. Codex owns per-session fan-out and each
  provider owns its actual quota; the proxy retains only lifecycle drain
  accounting and provider-scoped cooldown after an observed HTTP 429.
- Reconstruct the installed product as one native `codex-responses-proxy`
  command under a standard `src/` package, with semantic `cli`, `lifecycle`,
  `protocol`, `providers`, `relay`, and `service` owners. Repository-only
  release and Forge tooling is no longer shipped as product runtime.
- Retain exact read-only provider model-catalog routes and close connections for
  local rejections emitted before a request body is consumed.
- Stop serializing a healthy provider route. Per-route admission was fixed at
  one exchange since the UCloud upstream was returning HTTP 429; that upstream
  no longer rate-limits, and on the live listener every route acquisition
  reported `active=1/8`, so the process-wide bound was never the binding one.
  Holds of 23 to 69 seconds queued behind each other for up to 115 seconds
  without denying anything, which is invisible to every counter and visible only
  as latency to a client carrying its own deadline. The per-route width is now
  derived from the process-wide limit, so one route may hold at most half of
  process capacity and a second route always retains at least as much as the
  busiest route holds.
- Make the per-route width a validated operator setting,
  `CODEX_RESPONSES_PROXY_RESPONSES_MAX_PER_ROUTE`, bounded `1..4096` and
  rendered into the supervised unit. It was previously the only admission bound
  that was a source constant. Setting it to `1` restores the previous strict
  single-flight behavior without a new release, which is the recorded remedy if
  a provider begins rate-limiting again: because a provider cooldown is recorded
  only after an exchange returns, up to one route width of same-route requests
  can reach a newly rate-limiting provider before the first failure closes the
  cooldown for the rest.

### Fixed

- Bind native handoff teardown to the PID generation captured at authenticated
  health. Windows now releases every mapped bundle module before payload removal
  even when argv becomes unreadable during exit, while PID reuse remains
  fail-safe.
- Make hosted Git fixtures independent of the machine's default branch.
- Retain and terminate every authenticated native handoff successor before
  releasing its temporary payload, including when process inventory misses it.
- Derive commit-subject verification from the first integration ref available as
  a HEAD ancestor in the current checkout. Local Work Lanes still prefer
  `candidate/dev`, while GitLab and GitHub tag checkouts no longer require a
  forbidden remote candidate ref.
- Tolerate only transient Windows mapped-module locks while native handoff
  fixtures remove their verified temporary payload, preserving bounded failure
  when a lock persists.
- Normalize the host `commonpath` result before Windows bundle containment
  comparison and keep POSIX symlink materialization on compatible filesystems.
- Compare resolved native-bundle containment through the host filesystem's
  canonical path identity. Windows no longer rejects an internal member whose
  resolved path differs only by case, while real escapes remain fail-closed.
- Preserve the terminal newline when GitHub materializes an OpenSSH private-key
  text secret, and report the actionable OpenSSH rejection without a Python
  traceback.
- Validate release preparation from each Forge's own tag namespace. A GitLab tag
  pipeline no longer executes a GitHub-history assertion; cross-Forge
  consistency remains a read-only post-publication audit.
- Preserve live Responses bytes, including encrypted reasoning and collaboration
  control data, until Codex completes the current turn. Strip provider-bound
  ciphertext and identifiers only when a later request replays prior output,
  restoring non-empty subagent task delivery without weakening `store=false`.
- Bundle every native service adapter and keep expected failures concise, with
  no traceback, warning, module path, or private path.
- Discover process identity through bundled `psutil`, not host command parsers.
- Commit a prepared handoff before returning HTTP 202, so controller loss cannot
  strand the successor.
- Keep repository hooks portable and Python package coverage above 95 percent.
- Reject an upstream stream whose replay envelope cannot be projected safely,
  returning one bounded retryable error instead of forwarding an unproved
  provider-portable structure into the client conversation.
- Publish GitLab assets and its formal Release without querying GitHub. Each
  Forge now completes its own build, signature, asset, and Release workflow
  independently.
- Give a packaged successor up to 60 seconds to assume the listener during
  native handoff acceptance, removing the Windows startup false failure while
  preserving a bounded deadline.
- End the connection on a local response the listener emits before it reads the
  request body. Because the listener speaks HTTP/1.1, a closed-route rejection,
  an unsupported-method rejection, or the drain toggle previously left the
  unread body in the socket and then parsed it as the next request line, so one
  refused request produced two responses: the intended 404 and a spurious
  `400 Bad request syntax` synthesized from the caller's own JSON. A client
  reusing that connection lost its next request. A response emitted after the
  body is consumed still keeps the connection reusable.
- State the provider route table once in the specification. The Responses
  admission requirement restated the routing rule and still claimed that only
  `/v1/responses` targets resolve and that a non-Responses endpoint is rejected,
  which the admitted read-only `GET /<provider>/v1/models` route had made false.
  Routing is now owned by the route requirement alone, so a future admitted path
  cannot recreate the contradiction.
- Name the provider route and both admission limits in the local queue-timeout
  error instead of the process-wide concurrency gauge. A saturated single-flight
  route now reports which route is busy and that its own limit is one, so the
  message can no longer be read as eight concurrent requests when only one is in
  flight.
- Bound one streaming turn by the configured upstream timeout as a total
  wall-clock deadline, and release an upstream connection once its stream is
  abandoned or replaced. A stalled upstream that holds its socket open can no
  longer keep a provider-route admission slot past that deadline, which
  previously degraded into an unbounded series of per-read idle timeouts.
- Advertise `Retry-After: 5` on the local queue-timeout 503 and document the
  symptom. The response is retryable but its release time is bounded only by the
  total upstream stream deadline, so the hint is a deliberate floor rather than
  the transient-fault `Retry-After: 3` used by the upstream exhaustion paths.
- Document how to actually apply the queue-timeout knob when legitimate long
  turns keep exhausting the wait. The installed native unit pins the
  install-time value, so exporting
  `CODEX_RESPONSES_PROXY_RESPONSES_QUEUE_TIMEOUT` in a shell never reaches a
  supervised listener; re-rendering the unit is the supported path.
- Derive the default local queue wait from the total upstream stream deadline
  instead of restating an unrelated shorter constant. A request queued behind a
  route-slot holder is no longer denied while that holder is still inside its
  own deadline, which a census of the live logs measured as the cause of a 10.2
  percent denial rate: the median denied request needed only 24 seconds more
  than the old wait allowed. The operator override and its validated bounds are
  unchanged, and per-route admission stays single-flight.
- Add the closed, read-only `GET /<provider>/v1/models` compatibility route for
  DMXAPI, UCloud/Azure, and AIHubMix. Catalog requests retain client
  authentication and relay their selected upstream response exactly once,
  without entering Responses replay projection, admission, cooldown, retry, or
  recovery.

## 2.0.7 - 2026-08-02

History: [GitLab][2.0.7-gitlab] · [GitHub][2.0.7-github]

### Changed

- Retain the signed `v2.0.6` tags and failed hosted GitLab jobs as immutable
  evidence. `v2.0.6` was not eligible for installation; `v2.0.7` is the
  forward-only publication candidate carrying the portable coverage repair.

### Fixed

- Exercise the successful Darwin native-argument parser with a synthetic
  `sysctl` contract on every host, including incomplete-payload rejection, and
  verify the Darwin default state root without depending on the CI host. Linux
  quality jobs therefore retain branch coverage above 95 percent while real
  process integration remains Darwin-only.
- Render launchd test expectations with native path semantics and reuse the
  already-collected process command inventory on Windows and Linux. Windows
  handoff verification no longer launches one PowerShell/CIM query per host PID,
  while Darwin retains native argv identity and every signal path still
  revalidates the live PID immediately before mutation.
- Serialize active Responses exchanges within each configured provider route
  while preserving cross-route concurrency inside the existing global bound. A
  queued request rechecks provider cooldown before remote I/O, closing the
  concurrent burst window after an upstream HTTP 429 without adding retries.
- Run the native Darwin process-argument integration contract only on Darwin;
  Linux CI no longer invokes a nonexistent `sysctl` symbol through a mocked
  platform value.

## 2.0.5 - 2026-08-02

History: [GitLab][2.0.5-gitlab] · [GitHub][2.0.5-github]

### Fixed

- Preserve exact macOS process identity by reading native process arguments
  instead of reparsing the lossy `ps` command string. Installed paths containing
  spaces are now discovered, handed off, and terminated by exact resolved
  entrypoint identity.
- Bootstrap the package root before a watchdog launched as a direct script
  imports the runtime package. Rename runtime modules that collided with the
  Python standard library, removing the collision class rather than retaining a
  bootstrap-only workaround.
- Persist watchdog pre-logging failures to a bounded product-state stderr file
  and create its parent directory before launchd registration, so first-install
  crash loops are observable instead of silently discarded.
- Verify private GitLab Release assets through the authenticated `glab api`
  transport while retaining byte-for-byte cross-Forge asset comparison.
- Replace ambient PATH and user-site quality tools with a repository-owned,
  `uv.lock`-pinned `.venv`; both Forge projections invoke the same gate, and
  statement and branch coverage remain strictly above 95 percent.

## 2.0.4 - 2026-08-02

History: [GitLab][2.0.4-gitlab] · [GitHub][2.0.4-github]

### Fixed

- Admit the exact installed v2.0.0 protocol-v2 projection, including deployments
  created before `release-install-state.json` was finalized, while retaining
  canonical receipt, release, full-inventory, per-file digest, serving
  aggregate, and optional installed-state verification. Upgrade rollback
  restores both the retired `replay/event.py` byte and the original absence of
  finalized state.
- Make port 8792 the single runtime default without making it a fixed port.
  Installer, control, and uninstall `--port` options and
  `CODEX_RESPONSES_PROXY_PROXY_PORT` remain authoritative explicit overrides;
  production code is checked against copied 8791 or 8792 literals.

## 2.0.3 - 2026-08-02

History: [GitLab][2.0.3-gitlab] · [GitHub][2.0.3-github]

### Fixed

- Keep provider and request-fingerprint cooldown deadlines monotonic: a later
  concurrent failure with a shorter delay can no longer replace a still-active
  longer deadline and reopen upstream traffic prematurely.

## 2.0.2 - 2026-08-02

History: [GitLab][2.0.2-gitlab] · [GitHub][2.0.2-github]

### Changed

- Retain the signed `v2.0.1` tags and their failed hosted jobs as immutable
  evidence. No `v2.0.1` provider Release was published or installed; `v2.0.2` is
  the forward-only publication candidate carrying the repair.
- Rename the product and Python namespace from the DMX-specific Codex DMX Proxy
  to Codex Responses Proxy. The data plane now serves ordinary Responses
  endpoints through a provider manifest, so adding a gateway is a bounded
  provider-policy change rather than a product-wide special case.
- Make the product boundary explicit and enforceable: AIGW owns credentials,
  endpoint selection, and client projection; the proxy owns only Responses
  compatibility, its released payload, native supervision, status, and
  same-payload reload. Installation and removal no longer read, rewrite, or
  restore Codex or AIGW configuration.
- Replace the legacy Codex-private runtime layout and DMX-specific service
  identity with portable product-owned data, state, log, and supervision
  locations on macOS, Linux, and Windows.
- Remove the unscoped `/v1` compatibility route and runtime provider-manifest
  override. The release-owned manifest is now the sole provider authority, and
  every request selects an explicit `/<provider>/v1` namespace.
- Supersede the provider-specific commit-history rewriting model recorded for
  1.0.29. Version 2 uses one immutable, contributor-signed commit graph on both
  Forges; only native tag and Release actors are Forge-specific, and all
  identity and trust inputs remain external to product source.

### Fixed

- Select GitHub's provider-native release chronology in every metadata-test
  branch, including an already-tagged release checkout. This preserves strict
  canonical GitLab history checks while preventing the `v2.0.1` GitHub tag job
  from misclassifying provider-external tags and emitting a traceback.
- Bind the loopback listener without a reverse-DNS/FQDN lookup. Listener
  admission no longer stalls on hosts whose local DNS is slow or unavailable,
  including hosted macOS verification runners.
- Select supported Python 3.12, 3.13, and 3.14 lines in hosted CI instead of
  pinning platform-specific patch builds that are not published for every runner
  image.
- Project successful non-stream Responses atomically with the same
  provider-neutral ciphertext rules as SSE, and fail locally before downstream
  commitment on empty, truncated, malformed, failed, or otherwise non-terminal
  HTTP 2xx bodies.
- Reject empty Responses request bodies and ambiguous provider request targets
  before upstream I/O. Only exact `/<provider>/v1/responses` routes with an
  optional query are admitted.
- Replace the DMX-shaped registry interface with one optional `WirePolicy`
  boundary and admit request-changing `response_failed` recovery only from
  structured error fields, never incidental human-readable prose.
- Relay an upstream HTTP 429 after exactly one upstream call, preserve its body
  and eligible headers, and apply a bounded process-local cooldown only to that
  provider instead of multiplying throttling through the generic retry loop.
- Reduce the default Responses concurrency from 64 to 8 as a conservative burst
  guardrail. The validated environment override remains available; this default
  does not claim any provider's unpublished quota.
- Preserve the payload-free Codex 0.146 `compaction_trigger` request control
  through provider-portable replay projection, while continuing to reject
  unknown control fields before upstream I/O. This prevents short conversations
  from failing at their first automatic remote-compaction boundary.
- Preserve valid replay semantics without changing Codex JSONL, SQLite,
  historical messages, stored item identifiers, or model metadata. Provider
  neutral projection now owns the single replay grammar; the DMXAPI policy owns
  only exact HTTP 477 classification, one byte-identical retry of the current
  projected attempt, cooldown identity, and terminal 503 normalization.
- Include the provider manifest in every released payload, digest, handoff,
  installation, and recovery identity so runtime behavior cannot drift from the
  admitted release.

## 1.0.45 - 2026-07-31

History: [GitLab][1.0.45-gitlab] · [GitHub][1.0.45-github]

### Fixed

- Preserve correctly paired function and custom-tool history when a tool
  returned no textual output by projecting one explicit empty-result marker in
  the outbound request copy, while retaining the local rejection of empty
  ordinary dialogue and every malformed or unpaired replay shape.

## 1.0.44 - 2026-07-30

History: [GitLab][1.0.44-gitlab] · [GitHub][1.0.44-github]

### Fixed

- Project textual assistant and synthesized-agent history through the
  provider-neutral Easy Input Message string carrier, preserve refusal text,
  strip output-only metadata, and keep instruction, user, and tool content on
  input grammar so third-party Responses validators do not receive incomplete
  output-message hybrids.
- Preserve the same assistant carrier through the bounded DMX empty-response
  retry and insert explicit portable markers for root-only agent or tool
  ciphertext instead of emitting empty replay items.
- Record AIGW route state as schema v3 with an explicit `dmxapi`, `ucloud`, or
  `aihubmix` provider route and its matching scoped loopback endpoint. Keep the
  unscoped `/v1` URL bounded to direct-Codex compatibility, migrate schema-v2
  state only through `adopt-aigw`, and parse scoped custom ports structurally.

## 1.0.43 - 2026-07-30

History: [GitLab][1.0.43-gitlab] · [GitHub][1.0.43-github]

### Fixed

- Project every Responses replay request onto a provider-portable grammar,
  removing stored item identifiers, reasoning/search state, and opaque agent or
  tool ciphertext without changing Codex conversation storage.
- Add fixed, isolated loopback routes for DMXAPI, UCloud/Azure, and AIHubMix;
  keep DMX HTTP 477 recovery and cooldown scoped to DMXAPI.
- Sanitize streamed opaque output, reject unproved replay structures locally,
  validate upstream overrides as credential-free HTTPS origins, and isolate
  test-only loopback upstream injection from the released runtime.

## 1.0.42 - 2026-07-30

History: [GitLab][1.0.42-gitlab] · [GitHub][1.0.42-github]

### Fixed

- Align all canonical recovery contracts with the released two-projection
  identity model: rollback serving identity plus committed candidate manifest.
- Admit each provider signing key once per complete history projection instead
  of starting a Keychain-backed agent for every rewritten commit.

## 1.0.41 - 2026-07-30

History: [GitLab][1.0.41-gitlab] · [GitHub][1.0.41-github]

### Fixed

- Verify recovery as two simultaneous projections: the old listener's frozen
  serving identity and the newer candidate manifest already committed on disk.
  This makes preserved cross-version transactions recoverable without weakening
  snapshot, process, or publication checks.

## 1.0.40 - 2026-07-30

History: [GitLab][1.0.40-gitlab] · [GitHub][1.0.40-github]

### Fixed

- Admit the exact pinned quality-tool semantic version when stable executables
  append space-delimited informational build metadata.
- Reject different versions and misleading prefixes without weakening the
  repository-owned quality gate.

## 1.0.39 - 2026-07-30

History: [GitLab][1.0.39-gitlab] · [GitHub][1.0.39-github]

### Fixed

- Limit the shell executable-lookup fixture to POSIX hosts while retaining the
  complete Windows product matrix, so Windows does not misinterpret POSIX
  executable-bit semantics as a product failure.

## 1.0.38 - 2026-07-30

History: [GitLab][1.0.38-gitlab] · [GitHub][1.0.38-github]

### Fixed

- Validate the quality gate through its semantic owner instead of requiring an
  obsolete private shell pattern, preventing a correct exact-version resolver
  from failing release metadata verification.
- Run GitLab Debian dependency bootstrap explicitly noninteractively and
  quietly, eliminating debconf frontend fallback warnings from release logs.
- Validate protocol-v2 upgrade requests against the complete committed successor
  payload rather than the old listener's frozen runtime identity, so a real
  cross-version handoff no longer fails with HTTP 409.
- Add an explicit, publication-gated recovery rollback and a separately
  authorized verified-listener bootstrap. A damaged recovery remains retained;
  bootstrap failure restores the prior payload and must prove the prior runtime
  rather than claiming success.
- Resolve bare quality-tool commands by the exact required version across PATH,
  preventing an outer proof runner's virtual environment from silently
  substituting its own Ruff or ty while preserving explicit CI tool paths.

## 1.0.36 - 2026-07-30

History: [GitLab][1.0.36-gitlab] · [GitHub][1.0.36-github]

### Fixed

- Close failed handoff HTTP responses explicitly and confine intentional peer
  disconnect handling to the loopback test server, eliminating the leaked
  `ResourceWarning` and `socketserver` traceback seen in otherwise successful
  Python 3.14 and GitLab jobs.
- Make the canonical Python runner fail on warnings, unhandled traceback text,
  and `socketserver` exception banners; compile through an isolated bytecode
  prefix, disable retained Ruff caches, and declare the GitLab container's pip
  root-user policy explicitly.
- Use the same compile-and-test entrypoint across Python 3.12, 3.13, and 3.14 on
  GitLab, GitHub macOS, and GitHub Windows so green hosted jobs also prove clean
  diagnostic output.

## 1.0.35 - 2026-07-29

History: [GitLab][1.0.35-gitlab] · [GitHub][1.0.35-github]

### Fixed

- Make one-time legacy bootstrap accept only digest-verified historical
  schema-1/2 projections, derive the retired entrypoint from that same proof,
  and bind quiet-window and termination checks to the old listener path rather
  than the new semantic-package entrypoint.
- Replace native supervision after the old listener exits and before successor
  proof. A failed successor now restores old owned bytes, old supervision, and
  accepting historical runtime proof; an unproven restoration fails explicitly.
  Force mode still cannot bypass manifest or process-identity verification.
- Validate types with current stable `ty 0.0.65` across local and both Forge
  quality gates.

## 1.0.34 - 2026-07-29

History: [GitLab][1.0.34-gitlab] · [GitHub][1.0.34-github]

### Fixed

- Align real handoff successor observation with the runtime contract: an exact
  positive-PID successor remains valid after it advances from the transient
  `serving` state to the stable `finalized` state.
- Move GitHub's dependency wait to a bounded read-only hosted gate so the
  repository's sole trusted runner remains available for tag verification.
- Keep Git tag proof authentication provider-neutral: isolated fetches now use
  only the explicitly supplied remote transport instead of injecting `glab` as
  an implicit credential helper.

## 1.0.32 - 2026-07-29

History: [GitLab][1.0.32-gitlab] · [GitHub][1.0.32-github]

### Fixed

- Restore the exact annotated GitHub tag object after checkout and bind its
  peeled commit before tag verification or Release publication.

## 1.0.31 - 2026-07-29

History: [GitLab][1.0.31-gitlab] · [GitHub][1.0.31-github]

### Changed

- Close the released-source admission race by checking clean state before live
  publication verification and again during admission, then binding and
  rechecking `HEAD`, tag object, tag commit, tree, object format, and immutable
  Git blobs before the one-use payload capability is minted.
- Require exact Python `argv[1]` process identity before watchdog or listener
  termination, re-read identity before signalling, and prove within a fixed time
  limit that the original identity exited. Uninstall now proves native-service
  absence before payload mutation; purge removes only manifest-owned files,
  preserves unknown content, and reports incomplete cleanup with a nonzero exit.
- Replace the flat split package with the single semantic `codex_dmx_proxy`
  product root and make the serving inventory and digest one release-owned
  contract.
- Limit retired-layout migration and rollback to files proved owned by the
  previous manifest; preserve unknown contents and remove only empty retired
  directories.
- Make complete provider commit provenance a release invariant. GitLab now uses
  `Yang HENG <heng.yang.ds@hotmail.com>` and GitHub uses
  `Yang HENG <hengyang.2003@tsinghua.org.cn>` for both author and committer on
  every commit reachable from `main`; every such commit is SSH-signed and must
  be reported as `Verified` by its Forge.
- Replace signature-stripping identity rewriting with an isolated, leased DAG
  rebuild that preserves each source tree, parent topology, message, author
  date, and committer date while re-signing every commit. Dual-Forge parity now
  rejects an unsigned commit or a non-provider author/committer anywhere in the
  reachable history.
- Enforce combined, statement-only, and branch-only coverage independently at
  95%, derive the Python quality scope from one source inventory, and remove
  installed-control legacy bootstrap residue.

### Fixed

- Give every GitLab release-stage checkout complete provider history, so exact
  tag verification and Release publication enforce the same chronology as the
  main metadata gate.
- Normalize canonical tag creation timestamps to UTC before comparing them with
  Changelog release dates, so a signed tag created across local midnight
  preserves the repository's UTC release chronology.
- Give the real rolling-handoff integration proof enough hosted-runner margin to
  observe the successor without weakening its exact identity checks.

## 1.0.28 - 2026-07-29

History: [GitLab][1.0.28-gitlab] · [GitHub][1.0.28-github]

### Changed

- Establish `pyproject.toml` as the Python metadata and quality configuration
  carrier while keeping `VERSION` as the sole release-version owner. Add one
  repository-owned Ruff, formatting, type, public-docstring, code-size, and
  product branch-coverage gate plus Python 3.12/3.13/3.14 regression matrices.
- Make source-side `install.py` the sole payload-mutation entry. It now requires
  an in-repository proof of both provider-native signed tags, required CI, and
  formal Release records, then independently admits the clean exact signed tag
  under an external anchor. Immutable Git blobs move through an opaque one-use
  release capability into a private rollback transaction with a canonical
  receipt, manifest, aggregate serving identity, installed-release state, and
  explicit recovery hold.
- Remove release archives, working-tree stages, installed-control upgrades, and
  controller-only partial applies from supported installation surfaces.
  Installed control retains read-only evidence, route operations, and
  same-installed-payload reload; a different release is installed only by the
  source-side transaction.
- Bind fresh install, protocol-v2 handoff, rollback, and post-operation evidence
  to release, aggregate serving-payload digest, release-receipt digest, manifest
  digest, and accepting listener state. Unknown committed outcomes are preserved
  as `recovery_required` rather than reported as success.
- Restrict `--allow-legacy-bootstrap` and `--force-legacy-bootstrap` to the
  source-side first replacement of a verified pre-v2 listener. Neither flag is
  an installed-control reload or a normal protocol-v2 operating mode.

### Fixed

- Install Git and OpenSSH in every GitLab Python and quality job that executes
  signed-release-source tests, and accept both supported `ty 0.0.56` version
  output forms. This closes the hosted-only gap exposed by the failed `v1.0.27`
  tag pipeline without weakening or skipping the signing tests.
- Recover only the exact third-party Responses `Invalid 'input'` union
  validation contract with one strictly smaller, network-only current-dialogue
  request. The recovery retains the latest system, developer, and user messages
  in their original order, preserves top-level instructions, removes stale
  provider bindings, and never chains into another retry policy.
- Isolate this compatibility policy behind a dedicated pure-policy module, with
  bounded value-free diagnostics, exact call/output pairing checks, and stable
  terminal counters. Structural diagnostics erase unknown labels and values and
  bucket collection sizes before hashing; recovery events still report exact
  byte lengths and retained/dropped item counts without recording their values.

## 1.0.26 - 2026-07-27

History: [GitLab][1.0.26-gitlab] · [GitHub][1.0.26-github]

### Fixed

- Normalize exact replayed `output_text` blocks to the request-side `input_text`
  representation during the bounded HTTP 477 empty-response fallback. Unknown,
  enriched, image, and encrypted content remains rejected without a fallback
  replay.
- When exact stale search items make the semantic-preserving projector reject
  otherwise representable history, fall back once to all preceding system and
  developer instructions plus the final user message. Arbitrary unknown or
  unrepresentable history and state after that user message remain rejected.
- Reject a stale pending-release date before signing a release tag, so an
  offline release preparation cannot create a tag that will fail Forge
  provenance checks.
- Treat the exact DMX/OpenAI-shaped HTTP 400 `invalid_prompt` response whose
  message is `Request blocked` as a bounded historical-replay rejection. It now
  uses the existing strictly shrinking, tool-pair-safe recovery path; unrelated
  `invalid_prompt` responses remain terminal and unchanged.

## 1.0.25 - 2026-07-23

History: [GitLab][1.0.25-gitlab] · [GitHub][1.0.25-github]

### Added

- Add one semantic-preserving compatibility attempt after an exact DMX HTTP 477
  `empty_response`. The original sanitized request remains the first upstream
  body; the fallback preserves message phases and ordered function/custom-tool
  calls and outputs, and fails closed on unknown or unrepresentable history.
- Add a policy-versioned, TTL- and capacity-bounded cooldown keyed by the
  sanitized original request, without retaining request content or exposing
  fingerprints in runtime evidence.
- Add protocol-v2 listener handoff with explicit `PREPARE`, `READY`, `COMMIT`,
  `SERVING`, `FINALIZE`, and `ABORT` phases. POSIX transfers the listener with
  `pass_fds`; Windows transfers `socket.share()` bytes only through the child
  control pipe and restores them with `socket.fromshare()`.
- Configure Linux, macOS, and Windows candidate verification for Python 3.12,
  3.13, and 3.14. Windows execution remains a CI evidence gate, not physical
  Scheduled Task host acceptance.
- Add the portable, read-only `governance.py` evidence command to the installed
  payload. It reports only the existing manifest, listener, route, and runtime
  evidence; it does not inspect or modify AIGW, Codex history, credentials, or
  the proxy listener.
- Add `scripts/observe-reliability.py`, a source-side, secret-free observer for
  comparable `control.py status --json` snapshots. It separates upstream
  empty-response, upstream 5xx, and `response_failed` bursts from local stream
  failures, drain rejections, listener integrity, and restart boundaries;
  thresholds are explicit, bounded, and tested.

### Changed

- Add deterministic fake-upstream and real-subprocess coverage for first-body
  fidelity, one-shot 477 recovery, cooldown isolation, state transitions,
  rollback, active-flow completion, lease expiry, and repeated POSIX handoff.
- Validate the Windows watchdog lifecycle on a real host: a killed watchdog
  relaunches from the repeating time trigger, uninstall stops the running
  watchdog, and the task runs windowless. Under a real standard-user interactive
  logon the watchdog auto-starts and runs with a non-elevated least-privilege
  token. See
  [docs/evidence/windows-real-machine-validation.md](docs/evidence/windows-real-machine-validation.md).
- Add deterministic offline transport coverage for exhausted pre-content SSE,
  bounded/redacted logging, drain admission rejection, in-flight completion,
  timeout rollback, and fail-open drain-lease expiry.
- Add lifecycle regression coverage for quiet-window admission, busy-window
  refusal without drain, and listener identity changes at the final handoff.
- Add regression coverage for legacy bootstrap admission and its no-downgrade
  boundary when a current listener's atomic drain fails.
- Add regression coverage that the emergency compatibility path still refuses
  unverified payloads.

### Fixed

- Return a standard retryable HTTP 503 with `Retry-After: 3` when the 477
  fallback is unsafe, its one follow-up attempt fails, or an identical request
  is in cooldown, including requests that asked for streaming output.
- Stop the old accept loop before committing a prepared replacement, verify the
  child by PID, transaction, release, source, and manifest, and bound old-flow
  drain. Failed pre-finalize transactions confirm child exit before restoring
  old admission; unconfirmed aborts fail closed instead of risking dual accept.
- Preserve the existing bounded drain/terminate path for the first migration
  from an installed pre-v2 `1.0.24` listener, while subsequent v2 reloads and
  upgrades use the transactional handoff.
- Relaunch the Windows watchdog when the watchdog process itself is killed. The
  scheduled task's `RestartOnFailure` only reacts to a failed task launch, not
  to the launched watchdog being terminated later, so on a real host a killed
  watchdog was never brought back until the next logon. The repeating
  `TimeTrigger` now fires every minute; paired with `IgnoreNew`, a re-fire is a
  no-op while the watchdog is alive and relaunches it when it has died.
- Stop the running Windows watchdog during `uninstall`. `schtasks /delete`
  removes only the task definition, not an already-running instance, so the
  surviving watchdog immediately respawned the proxy after uninstall stopped it.
  Uninstall now terminates the watchdog matched to this install's own launcher
  and script paths before removing the task.
- Run the Windows watchdog windowless. The former `cmd.exe /c` launcher kept a
  visible console window for the whole watchdog lifetime because it waits on the
  windowless child; the task now runs a generated `.pyw` bootstrap directly with
  `pythonw.exe`, so no console is allocated.
- Remove pre-retention `reject-*.json` raw request captures during installation
  and payload refresh, while preserving the bounded, redacted operational logs.
- Add a narrow, transactional controller-only lifecycle apply path for an
  already-running, drain-capable listener. It refuses any source change outside
  `control.py`, verifies and updates the manifest while the existing listener
  remains in normal admission, leaves active Responses streams untouched, and
  reports the installed controller SHA-256.
- Converge CI to one repository-scoped GitHub runner and one separate
  project-scoped GitLab runner. GitHub verification and release now share the
  `codex-dmx-proxy-github-macos-arm64` registration, while GitLab jobs require
  the dedicated `codex-dmx-proxy-gitlab-ci` tag.
- Start the formal `1.0.22` source train instead of adopting the previously
  installed `1.0.21` candidate as a release: its payload was recoverable, but it
  lacked source-repository provenance and was therefore not publishable.
- Record the aggregate serving-payload SHA-256 captured when the listener loaded
  the exact same-root executable module set, so loopback health distinguishes a
  new on-disk deployment from a running old process.
- Replace the single-sample reload gate with an atomic loopback drain barrier.
  It rejects new Responses requests while admitted work finishes, requires the
  same listener to report `draining=true` and `active_responses=0` before
  replacement, and fails open through a bounded lease if lifecycle control
  disappears.
- Wait for a bounded zero-active quiet window before closing admission for a
  normal reload or upgrade. A busy listener now remains fully serving and the
  lifecycle command refuses without emitting a burst of maintenance 503s.
- Bootstrap the first upgrade from a pre-drain listener only after explicit
  operator authorization and a narrowly scoped two-sample, five-second idle
  window from the same verified PID. It refuses on new activity, health loss,
  timeout, or PID change; all subsequent lifecycle actions use atomic drain.
- Restrict an emergency forced legacy bootstrap to separately authorized
  upgrade-only use after manifest integrity and single-listener verification;
  ordinary reload never receives this interruption path.
- Return retryable HTTP 503 with `Retry-After: 3` when all pre-content SSE
  reconnect attempts are exhausted, rather than returning an empty successful
  stream that the client must classify as a disconnection.
- Bound and rotate proxy and watchdog logs, redact secret-shaped diagnostic
  values, remove query values from logged request paths, and retire macOS
  launchd stdout/stderr sinks that created unbounded parallel logs.

## 1.0.15 - 2026-07-18

History: [GitLab][1.0.15-gitlab] · [GitHub][1.0.15-github]

### Fixed

- Pin GitLab release-tag identity and signer in a provider-native tag command,
  preventing a GitHub conditional Git identity from creating unverifiable GitLab
  provenance.

## 1.0.14 - 2026-07-18

History: [GitLab][1.0.14-gitlab] · [GitHub][1.0.14-github]

### Added

- Expose a loopback-only, secret-free runtime reliability snapshot through
  `control.py status --json` and `GET /healthz`, with counters for stream
  outcomes, bounded recovery, replay sanitization, and upstream classes.
- Add a read-only dual-forge parity auditor that verifies tree parity,
  provider-specific identities and signatures, and branch/worktree hygiene.

### Changed

- Add bounded local-hop coverage for pre-content `response.failed` recovery,
  premature EOF recovery, and the no-retry-after-commit boundary.

### Fixed

- Remove request-body, header, and rejected-payload capture paths so local
  diagnostics retain only bounded classifications, identifiers, and byte counts.

## 1.0.13 - 2026-07-17

History: [GitLab][1.0.13-gitlab] · [GitHub][1.0.13-github]

### Changed

- Added regression coverage that proves GitHub tag creation invokes the
  configured SSH signing program instead of calling `ssh-keygen` directly.

### Fixed

- Make the GitHub-native tag command use the workstation's configured SSH
  signing program rather than bypassing its Keychain-aware signing bridge.

## 1.0.12 - 2026-07-17

History: [GitLab][1.0.12-gitlab] · [GitHub][1.0.12-github]

### Changed

- Added transport regression coverage for dialogue-only recovery, its exact
  retained-message boundary, response telemetry, and retryable exhaustion.
- Added transport-level regression coverage that proves a 477 `empty_response`
  is retried with byte-identical request data before a successful response is
  relayed, and is normalized to 503 only when the bounded retry budget is
  exhausted.
- Added regression coverage for sub-budget failures, impossible target budgets,
  staged reduction, pair integrity, latest-user retention, and fallback-only
  cache-key removal.
- Added independent GitLab and GitHub CI/CD contracts, provider-specific source
  projection, and formal release records. The project is now distributed under
  the MIT License.
- Make every GitLab release-metadata and tag gate force-refresh and prune the
  provider tag namespace before checking release chronology. This prevents a
  shared runner's deleted local tag from creating a false Changelog failure.
- Added an isolated regression fixture that proves
  `git fetch --tags --force --prune --prune-tags origin` removes a tag deleted
  from the remote.
- Require the GitLab release-metadata gate to use complete history before it
  tests an intentionally untagged release fixture, preventing shallow-clone
  history from masking the fixture's historical-release premise.

### Fixed

- After an explicit upstream `response_failed` rejects the bounded pair-safe
  fallbacks, make one final dialogue-only recovery request. It contains only the
  latest developer or system instruction before the active request, where one is
  present, and the latest user request; assistant and tool replay are omitted
  without changing stored Codex history.
- Return retryable HTTP 503 with `Retry-After: 3` after bounded
  `response_failed` recovery is exhausted, rather than returning the upstream
  HTTP 400 as a terminal client validation error.
- Treat the classified DMX HTTP 477 `empty_response` contract as a bounded
  upstream transient. The proxy retries the unchanged request and, only after
  that retry budget is exhausted, normalizes the condition to retryable HTTP 503
  with `Retry-After`; other 477 responses remain visible to the client
  unchanged.
- Apply staged, strictly shrinking pair-safe fallback attempts after an explicit
  upstream `response_failed`, including failures whose original request is
  already below the ordinary compaction ceiling. Each fallback retains the
  latest user context and complete tool call/output pairs.
- Preserve a compacted request during a pre-content SSE reconnect instead of
  reopening the original rejected replay body.

## 1.0.8 - 2026-07-14

History: [GitLab][1.0.8-gitlab] · [GitHub][1.0.8-github]

### Changed

- Added regression coverage for sub-budget failures, impossible target budgets,
  staged reduction, pair integrity, latest-user retention, and fallback-only
  cache-key removal.

### Fixed

- Apply staged, strictly shrinking pair-safe fallback attempts after an explicit
  upstream `response_failed`, including failures whose original request is
  already below the ordinary compaction ceiling. Each fallback retains the
  latest user context and complete tool call/output pairs.
- Preserve a compacted request during a pre-content SSE reconnect instead of
  reopening the original rejected replay body.

## 1.0.7 - 2026-07-14

History: [GitLab][1.0.7-gitlab] · [GitHub][1.0.7-github]

### Changed

- Added regression coverage for pair integrity, latest-user retention,
  fallback-only cache-key removal, no-safe-suffix behavior, and unrelated HTTP
  400 rejections.

### Fixed

- When an upstream gateway explicitly returns HTTP 400 with a Responses
  `response_failed` execution error, make up to three strictly shrinking
  adaptive fallbacks for replay context: remove only the oldest contiguous input
  prefix, preserve the latest user context and complete tool call/output pairs,
  and remove the stale `prompt_cache_key` only from fallback requests. Ordinary
  client-side 400 errors remain non-retryable.

## 1.0.6 - 2026-07-14

History: [GitLab][1.0.6-gitlab] · [GitHub][1.0.6-github]

### Fixed

- Treat upstream HTTP 524 gateway timeouts as bounded, transient failures,
  alongside 429 and 5xx responses.

## 1.0.5 - 2026-07-14

History: [GitLab][1.0.5-gitlab] · [GitHub][1.0.5-github]

### Fixed

- Formalized original-conversation recovery boundaries: lifecycle operations do
  not require a new conversation, a forced client quit, or session mutation.
- Kept AIGW as the sole owner of marked provider configuration; the proxy owns
  only the data-plane adapter and its local process lifecycle.

## 1.0.4 - 2026-07-14

History: [GitLab][1.0.4-gitlab] · [GitHub][1.0.4-github]

### Added

- Added a manifest for the installed runtime payload and a narrowly scoped
  listener reload that verifies replacement by the watchdog.

## 1.0.3 - 2026-07-14

History: [GitLab][1.0.3-gitlab] · [GitHub][1.0.3-github]

### Fixed

- Preserved required `agent_message` encrypted-content blocks while removing
  only replayed reasoning state. This fixes rejected payloads missing the
  required `encrypted_content` field.

## 1.0.2 - 2026-07-14

History: [GitLab][1.0.2-gitlab] · [GitHub][1.0.2-github]

### Fixed

- Removed only non-replayable local image references at the outbound boundary.
- Preserved custom Windows service parameters across logon.
- Added reversible route control, strict route-drift handling, and AIGW route
  delegation through AIGW's public CLI.

## 1.0.1 - 2026-07-08

History: [GitLab][1.0.1-gitlab] · [GitHub][1.0.1-github]

### Fixed

- Allowed installation to complete on minimal Linux environments that lack a
  user systemd bus and cron; the required manual persistence step is explicit.

## 1.0.0 - 2026-07-08

History: [GitLab][1.0.0-gitlab] · [GitHub][1.0.0-github]

### Added

- Introduced the portable loopback Responses compatibility adapter, watchdog,
  platform service adapters, bounded upstream retries, and SSE reconnect
  handling.

[Unreleased-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v4.0.5...main
[Unreleased-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v4.0.5...main
[4.0.5-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v4.0.4...v4.0.5
[4.0.5-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v4.0.4...v4.0.5
[4.0.4-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v4.0.3...v4.0.4
[4.0.4-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v4.0.3...v4.0.4
[4.0.3-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v4.0.2...v4.0.3
[4.0.3-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v4.0.2...v4.0.3
[4.0.2-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v4.0.1...v4.0.2
[4.0.2-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v4.0.1...v4.0.2
[4.0.1-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v4.0.0...v4.0.1
[4.0.1-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v4.0.0...v4.0.1
[4.0.0-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.17...v4.0.0
[4.0.0-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.17...v4.0.0
[3.1.17-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.16...v3.1.17
[3.1.17-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.16...v3.1.17
[3.1.16-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.15...v3.1.16
[3.1.16-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.15...v3.1.16
[3.1.15-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.14...v3.1.15
[3.1.15-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.14...v3.1.15
[3.1.14-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.13...v3.1.14
[3.1.14-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.13...v3.1.14
[3.1.13-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.12...v3.1.13
[3.1.13-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.12...v3.1.13
[3.1.12-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.11...v3.1.12
[3.1.12-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.11...v3.1.12
[3.1.11-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.10...v3.1.11
[3.1.11-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.10...v3.1.11
[3.1.10-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.9...v3.1.10
[3.1.10-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.9...v3.1.10
[3.1.9-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.8...v3.1.9
[3.1.9-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.8...v3.1.9
[3.1.8-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.7...v3.1.8
[3.1.8-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.7...v3.1.8
[3.1.7-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.6...v3.1.7
[3.1.7-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.6...v3.1.7
[3.1.6-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.5...v3.1.6
[3.1.6-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.5...v3.1.6
[3.1.5-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.4...v3.1.5
[3.1.5-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.4...v3.1.5
[3.1.4-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.3...v3.1.4
[3.1.4-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.3...v3.1.4
[3.1.3-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.2...v3.1.3
[3.1.3-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.2...v3.1.3
[3.1.2-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.1...v3.1.2
[3.1.2-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.1...v3.1.2
[3.1.1-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.1.0...v3.1.1
[3.1.1-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.1.0...v3.1.1
[3.1.0-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.0.5...v3.1.0
[3.1.0-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.0.5...v3.1.0
[3.0.5-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.0.4...v3.0.5
[3.0.5-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.0.4...v3.0.5
[3.0.4-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.0.3...v3.0.4
[3.0.4-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.0.3...v3.0.4
[3.0.3-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.0.2...v3.0.3
[3.0.3-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.0.2...v3.0.3
[3.0.2-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.0.1...v3.0.2
[3.0.2-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.0.1...v3.0.2
[3.0.1-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v3.0.0...v3.0.1
[3.0.1-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v3.0.0...v3.0.1
[3.0.0-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.58...v3.0.0
[3.0.0-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.58...v3.0.0
[2.0.58-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.57...v2.0.58
[2.0.58-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.57...v2.0.58
[2.0.57-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.56...v2.0.57
[2.0.57-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.56...v2.0.57
[2.0.56-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.55...v2.0.56
[2.0.56-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.55...v2.0.56
[2.0.55-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.54...v2.0.55
[2.0.55-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.54...v2.0.55
[2.0.54-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.53...v2.0.54
[2.0.54-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.53...v2.0.54
[2.0.53-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.52...v2.0.53
[2.0.53-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.52...v2.0.53
[2.0.52-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.51...v2.0.52
[2.0.52-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.51...v2.0.52
[2.0.51-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.50...v2.0.51
[2.0.51-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.50...v2.0.51
[2.0.50-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.47...v2.0.50
[2.0.50-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.47...v2.0.50
[2.0.47-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.46...v2.0.47
[2.0.47-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.46...v2.0.47
[2.0.46-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.45...v2.0.46
[2.0.46-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.45...v2.0.46
[2.0.45-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.44...v2.0.45
[2.0.45-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.44...v2.0.45
[2.0.44-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.43...v2.0.44
[2.0.44-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.43...v2.0.44
[2.0.43-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.42...v2.0.43
[2.0.43-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.42...v2.0.43
[2.0.42-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.41...v2.0.42
[2.0.42-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.41...v2.0.42
[2.0.41-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.40...v2.0.41
[2.0.41-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.40...v2.0.41
[2.0.40-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.39...v2.0.40
[2.0.40-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.39...v2.0.40
[2.0.39-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.38...v2.0.39
[2.0.39-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.38...v2.0.39
[2.0.38-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.37...v2.0.38
[2.0.38-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.37...v2.0.38
[2.0.37-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.36...v2.0.37
[2.0.37-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.36...v2.0.37
[2.0.36-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.35...v2.0.36
[2.0.36-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.35...v2.0.36
[2.0.35-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.34...v2.0.35
[2.0.35-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.34...v2.0.35
[2.0.34-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.33...v2.0.34
[2.0.34-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.33...v2.0.34
[2.0.33-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.32...v2.0.33
[2.0.33-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.32...v2.0.33
[2.0.32-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.31...v2.0.32
[2.0.32-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.31...v2.0.32
[2.0.31-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.30...v2.0.31
[2.0.31-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.30...v2.0.31
[2.0.30-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.29...v2.0.30
[2.0.30-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.29...v2.0.30
[2.0.29-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.25...v2.0.29
[2.0.29-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.25...v2.0.29
[2.0.25-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.24...v2.0.25
[2.0.25-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.24...v2.0.25
[2.0.24-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.7...v2.0.24
[2.0.24-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.7...v2.0.24
[2.0.7-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.5...v2.0.7
[2.0.7-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.5...v2.0.7
[2.0.5-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.4...v2.0.5
[2.0.5-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.4...v2.0.5
[2.0.4-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.3...v2.0.4
[2.0.4-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.3...v2.0.4
[2.0.3-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v2.0.2...v2.0.3
[2.0.3-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v2.0.2...v2.0.3
[2.0.2-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.45...v2.0.2
[2.0.2-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.45...v2.0.2
[1.0.45-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.44...v1.0.45
[1.0.45-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.44...v1.0.45
[1.0.44-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.43...v1.0.44
[1.0.44-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.43...v1.0.44
[1.0.43-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.42...v1.0.43
[1.0.43-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.42...v1.0.43
[1.0.42-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.41...v1.0.42
[1.0.42-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.41...v1.0.42
[1.0.41-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.40...v1.0.41
[1.0.41-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.40...v1.0.41
[1.0.40-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.39...v1.0.40
[1.0.40-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.39...v1.0.40
[1.0.39-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.38...v1.0.39
[1.0.39-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.38...v1.0.39
[1.0.38-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.36...v1.0.38
[1.0.38-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.36...v1.0.38
[1.0.36-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.35...v1.0.36
[1.0.36-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.35...v1.0.36
[1.0.35-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.34...v1.0.35
[1.0.35-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.34...v1.0.35
[1.0.34-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.32...v1.0.34
[1.0.34-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.32...v1.0.34
[1.0.32-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.31...v1.0.32
[1.0.32-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.31...v1.0.32
[1.0.31-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.28...v1.0.31
[1.0.31-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.28...v1.0.31
[1.0.28-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.26...v1.0.28
[1.0.28-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.26...v1.0.28
[1.0.26-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.25...v1.0.26
[1.0.26-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.25...v1.0.26
[1.0.25-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.15...v1.0.25
[1.0.25-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.15...v1.0.25
[1.0.15-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.14...v1.0.15
[1.0.15-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.14...v1.0.15
[1.0.14-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.13...v1.0.14
[1.0.14-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.13...v1.0.14
[1.0.13-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.12...v1.0.13
[1.0.13-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.12...v1.0.13
[1.0.12-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.8...v1.0.12
[1.0.12-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.8...v1.0.12
[1.0.8-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.7...v1.0.8
[1.0.8-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.7...v1.0.8
[1.0.7-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.6...v1.0.7
[1.0.7-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.6...v1.0.7
[1.0.6-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.5...v1.0.6
[1.0.6-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.5...v1.0.6
[1.0.5-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.4...v1.0.5
[1.0.5-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.4...v1.0.5
[1.0.4-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.3...v1.0.4
[1.0.4-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.3...v1.0.4
[1.0.3-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.2...v1.0.3
[1.0.3-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.2...v1.0.3
[1.0.2-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.1...v1.0.2
[1.0.2-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.1...v1.0.2
[1.0.1-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/compare/v1.0.0...v1.0.1
[1.0.1-github]:
    https://github.com/HengYangDS/codex-responses-proxy/compare/v1.0.0...v1.0.1
[1.0.0-gitlab]:
    http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-responses-proxy/-/tags/v1.0.0
[1.0.0-github]:
    https://github.com/HengYangDS/codex-responses-proxy/commits/v1.0.0
