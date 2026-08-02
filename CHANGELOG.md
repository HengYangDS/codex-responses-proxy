# Changelog

This project follows [Semantic Versioning](https://semver.org/). The changelog
records released, user-relevant behavior across both Forge planes. `Unreleased`
is reserved for work that has not yet been tagged. A provider may retain these
shared headings even when a historical tag exists only on the other Forge.

## [Unreleased]

## [2.0.7] - 2026-08-02

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

## [2.0.6] - 2026-08-02

### Fixed

- Serialize active Responses exchanges within each configured provider route
  while preserving cross-route concurrency inside the existing global bound.
  A queued request rechecks provider cooldown before remote I/O, closing the
  concurrent burst window after an upstream HTTP 429 without adding retries.
- Run the native Darwin process-argument integration contract only on Darwin;
  Linux CI no longer invokes a nonexistent `sysctl` symbol through a mocked
  platform value.

### Release history

- Retain the signed `v2.0.6` tags and failed hosted GitLab jobs as immutable
  evidence. `v2.0.6` was not eligible for installation; `v2.0.7` is the
  forward-only publication candidate carrying the portable coverage repair.

## [2.0.5] - 2026-08-02

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

## [2.0.4] - 2026-08-02

### Fixed

- Admit the exact installed v2.0.0 protocol-v2 projection, including deployments
  created before `release-install-state.json` was finalized, while retaining
  canonical receipt, release, full-inventory, per-file digest, serving aggregate,
  and optional installed-state verification. Upgrade rollback restores both the
  retired `replay/event.py` byte and the original absence of finalized state.
- Make port 8792 the single runtime default without making it a fixed port.
  Installer, control, and uninstall `--port` options and
  `CODEX_RESPONSES_PROXY_PROXY_PORT` remain authoritative explicit overrides;
  production code is checked against copied 8791 or 8792 literals.

## [2.0.3] - 2026-08-02

### Fixed

- Keep provider and request-fingerprint cooldown deadlines monotonic: a later
  concurrent failure with a shorter delay can no longer replace a still-active
  longer deadline and reopen upstream traffic prematurely.

## [2.0.2] - 2026-08-02

### Fixed

- Select GitHub's provider-native release chronology in every metadata-test
  branch, including an already-tagged release checkout. This preserves strict
  canonical GitLab history checks while preventing the `v2.0.1` GitHub tag job
  from misclassifying provider-external tags and emitting a traceback.

### Release history

- Retain the signed `v2.0.1` tags and their failed hosted jobs as immutable
  evidence. No `v2.0.1` provider Release was published or installed; `v2.0.2`
  is the forward-only publication candidate carrying the repair.

## [2.0.1] - 2026-08-02

### Fixed

- Bind the loopback listener without a reverse-DNS/FQDN lookup. Listener
  admission no longer stalls on hosts whose local DNS is slow or unavailable,
  including hosted macOS verification runners.
- Select supported Python 3.12, 3.13, and 3.14 lines in hosted CI instead of
  pinning platform-specific patch builds that are not published for every
  runner image.
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

## [2.0.0] - 2026-08-02

### Changed

- Rename the product and Python namespace from the DMX-specific Codex DMX
  Proxy to Codex Responses Proxy. The data plane now serves ordinary Responses
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
  installation, and recovery identity so runtime behavior cannot drift from
  the admitted release.

## [1.0.45] - 2026-07-31

### Fixed

- Preserve correctly paired function and custom-tool history when a tool
  returned no textual output by projecting one explicit empty-result marker in
  the outbound request copy, while retaining the local rejection of empty
  ordinary dialogue and every malformed or unpaired replay shape.

## [1.0.44] - 2026-07-30

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

## [1.0.43] - 2026-07-30

### Fixed

- Project every Responses replay request onto a provider-portable grammar,
  removing stored item identifiers, reasoning/search state, and opaque agent or
  tool ciphertext without changing Codex conversation storage.
- Add fixed, isolated loopback routes for DMXAPI, UCloud/Azure, and AIHubMix;
  keep DMX HTTP 477 recovery and cooldown scoped to DMXAPI.
- Sanitize streamed opaque output, reject unproved replay structures locally,
  validate upstream overrides as credential-free HTTPS origins, and isolate
  test-only loopback upstream injection from the released runtime.

## [1.0.42] - 2026-07-30

### Fixed

- Align all canonical recovery contracts with the released two-projection
  identity model: rollback serving identity plus committed candidate manifest.
- Admit each provider signing key once per complete history projection instead
  of starting a Keychain-backed agent for every rewritten commit.

## [1.0.41] - 2026-07-30

### Fixed

- Verify recovery as two simultaneous projections: the old listener's frozen
  serving identity and the newer candidate manifest already committed on disk.
  This makes preserved cross-version transactions recoverable without weakening
  snapshot, process, or publication checks.

## [1.0.40] - 2026-07-30

### Fixed

- Admit the exact pinned quality-tool semantic version when stable executables
  append space-delimited informational build metadata.
- Reject different versions and misleading prefixes without weakening the
  repository-owned quality gate.

## [1.0.39] - 2026-07-30

### Fixed

- Limit the shell executable-lookup fixture to POSIX hosts while retaining the
  complete Windows product matrix, so Windows does not misinterpret POSIX
  executable-bit semantics as a product failure.

## [1.0.38] - 2026-07-30

### Fixed

- Validate the quality gate through its semantic owner instead of requiring an
  obsolete private shell pattern, preventing a correct exact-version resolver
  from failing release metadata verification.
- Run GitLab Debian dependency bootstrap explicitly noninteractively and
  quietly, eliminating debconf frontend fallback warnings from release logs.

## [1.0.37] - 2026-07-30

### Fixed

- Validate protocol-v2 upgrade requests against the complete committed
  successor payload rather than the old listener's frozen runtime identity, so
  a real cross-version handoff no longer fails with HTTP 409.
- Add an explicit, publication-gated recovery rollback and a separately
  authorized verified-listener bootstrap. A damaged recovery remains retained;
  bootstrap failure restores the prior payload and must prove the prior runtime
  rather than claiming success.
- Resolve bare quality-tool commands by the exact required version across PATH,
  preventing an outer proof runner's virtual environment from silently
  substituting its own Ruff or ty while preserving explicit CI tool paths.

## [1.0.36] - 2026-07-30

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

## [1.0.35] - 2026-07-29

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

## [1.0.34] - 2026-07-29

### Fixed

- Align real handoff successor observation with the runtime contract: an exact
  positive-PID successor remains valid after it advances from the transient
  `serving` state to the stable `finalized` state.

## [1.0.33] - 2026-07-29

### Fixed

- Move GitHub's dependency wait to a bounded read-only hosted gate so the
  repository's sole trusted runner remains available for tag verification.
- Keep Git tag proof authentication provider-neutral: isolated fetches now use
  only the explicitly supplied remote transport instead of injecting `glab` as
  an implicit credential helper.

## [1.0.32] - 2026-07-29

### Fixed

- Restore the exact annotated GitHub tag object after checkout and bind its
  peeled commit before tag verification or Release publication.

## [1.0.31] - 2026-07-29

### Fixed

- Give every GitLab release-stage checkout complete provider history, so exact
  tag verification and Release publication enforce the same chronology as the
  main metadata gate.

## [1.0.30] - 2026-07-29

### Fixed

- Normalize canonical tag creation timestamps to UTC before comparing them
  with Changelog release dates, so a signed tag created across local midnight
  preserves the repository's UTC release chronology.
- Give the real rolling-handoff integration proof enough hosted-runner margin
  to observe the successor without weakening its exact identity checks.

## [1.0.29] - 2026-07-29

### Changed

- Close the released-source admission race by checking clean state before live
  publication verification and again during admission, then binding and
  rechecking `HEAD`, tag object, tag commit, tree, object format, and immutable
  Git blobs before the one-use payload capability is minted.
- Require exact Python `argv[1]` process identity before watchdog or listener
  termination, re-read identity before signalling, and boundedly prove the
  original identity exited. Uninstall now proves native-service absence before
  payload mutation; purge removes only manifest-owned files, preserves unknown
  content, and reports incomplete cleanup with a nonzero exit.
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

### Quality

- Enforce combined, statement-only, and branch-only coverage independently at
  95%, derive the Python quality scope from one source inventory, and remove
  installed-control legacy bootstrap residue.

## [1.0.28] - 2026-07-29

### Fixed

- Install Git and OpenSSH in every GitLab Python and quality job that executes
  signed-release-source tests, and accept both supported `ty 0.0.56` version
  output forms. This closes the hosted-only gap exposed by the failed
  `v1.0.27` tag pipeline without weakening or skipping the signing tests.

## [1.0.27] - 2026-07-29

### Fixed

- Recover only the exact third-party Responses `Invalid 'input'` union
  validation contract with one strictly smaller, network-only current-dialogue
  request. The recovery retains the latest system, developer, and user
  messages in their original order, preserves top-level instructions, removes
  stale provider bindings, and never chains into another retry policy.
- Isolate this compatibility policy behind a dedicated pure-policy module, with
  bounded value-free diagnostics, exact call/output pairing checks, and stable
  terminal counters. Structural diagnostics erase unknown labels and values and
  bucket collection sizes before hashing; recovery events still report exact
  byte lengths and retained/dropped item counts without recording their values.

### Quality

- Establish `pyproject.toml` as the Python metadata and quality configuration
  carrier while keeping `VERSION` as the sole release-version owner. Add one
  repository-owned Ruff, formatting, type, public-docstring, code-size, and
  product branch-coverage gate plus Python 3.12/3.13/3.14 regression matrices.

### Changed

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

## [1.0.26] - 2026-07-27

### Fixed

- Normalize exact replayed `output_text` blocks to the request-side
  `input_text` representation during the bounded HTTP 477 empty-response
  fallback. Unknown, enriched, image, and encrypted content remains rejected
  without a fallback replay.
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

## [1.0.25] - 2026-07-23

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
  scheduled task's `RestartOnFailure` only reacts to a failed task launch, not to
  the launched watchdog being terminated later, so on a real host a killed
  watchdog was never brought back until the next logon. The repeating
  `TimeTrigger` now fires every minute; paired with `IgnoreNew`, a re-fire is a
  no-op while the watchdog is alive and relaunches it when it has died.
- Stop the running Windows watchdog during `uninstall`. `schtasks /delete` removes
  only the task definition, not an already-running instance, so the surviving
  watchdog immediately respawned the proxy after uninstall stopped it. Uninstall
  now terminates the watchdog matched to this install's own launcher and script
  paths before removing the task.
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
  installed `1.0.21` candidate as a release: its payload was recoverable, but
  it lacked source-repository provenance and was therefore not publishable.
- Record the aggregate serving-payload SHA-256 captured when the listener loaded
  the exact same-root executable module set,
  so loopback health distinguishes a new on-disk deployment from a running old
  process.
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

### Verified

- Add deterministic fake-upstream and real-subprocess coverage for first-body
  fidelity, one-shot 477 recovery, cooldown isolation, state transitions,
  rollback, active-flow completion, lease expiry, and repeated POSIX handoff.
- Validate the Windows watchdog lifecycle on a real host: a killed watchdog
  relaunches from the repeating time trigger, uninstall stops the running
  watchdog, and the task runs windowless. Under a real standard-user interactive
  logon the watchdog auto-starts and runs with a non-elevated least-privilege
  token. See [docs/evidence/windows-real-machine-validation.md](docs/evidence/windows-real-machine-validation.md).
- Add deterministic offline transport coverage for exhausted pre-content SSE,
  bounded/redacted logging, drain admission rejection, in-flight completion,
  timeout rollback, and fail-open drain-lease expiry.
- Add lifecycle regression coverage for quiet-window admission, busy-window
  refusal without drain, and listener identity changes at the final handoff.
- Add regression coverage for legacy bootstrap admission and its no-downgrade
  boundary when a current listener's atomic drain fails.
- Add regression coverage that the emergency compatibility path still refuses
  unverified payloads.

## [1.0.15] - 2026-07-18

### Fixed

- Pin GitLab release-tag identity and signer in a provider-native tag command,
  preventing a GitHub conditional Git identity from creating unverifiable
  GitLab provenance.

## [1.0.14] - 2026-07-18

### Added

- Expose a loopback-only, secret-free runtime reliability snapshot through
  `control.py status --json` and `GET /healthz`, with counters for stream
  outcomes, bounded recovery, replay sanitization, and upstream classes.
- Add a read-only dual-forge parity auditor that verifies tree parity,
  provider-specific identities and signatures, and branch/worktree hygiene.

### Fixed

- Remove request-body, header, and rejected-payload capture paths so local
  diagnostics retain only bounded classifications, identifiers, and byte counts.

### Verified

- Add bounded local-hop coverage for pre-content `response.failed` recovery,
  premature EOF recovery, and the no-retry-after-commit boundary.

## [1.0.13] - 2026-07-17

### Fixed

- Make the GitHub-native tag command use the workstation's configured SSH
  signing program rather than bypassing its Keychain-aware signing bridge.

### Verified

- Added regression coverage that proves GitHub tag creation invokes the
  configured SSH signing program instead of calling `ssh-keygen` directly.

## [1.0.12] - 2026-07-17

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
  that retry budget is exhausted, normalizes the condition to retryable HTTP
  503 with `Retry-After`; other 477 responses remain visible to the client
  unchanged.
- Apply staged, strictly shrinking pair-safe fallback attempts after an explicit
  upstream `response_failed`, including failures whose original request is
  already below the ordinary compaction ceiling. Each fallback retains the
  latest user context and complete tool call/output pairs.
- Preserve a compacted request during a pre-content SSE reconnect instead of
  reopening the original rejected replay body.

### Verified

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
- Added an isolated regression fixture that proves `git fetch --tags --force
  --prune --prune-tags origin` removes a tag deleted from the remote.
- Require the GitLab release-metadata gate to use complete history before it
  tests an intentionally untagged release fixture, preventing shallow-clone
  history from masking the fixture's historical-release premise.

## [1.0.8] - 2026-07-14

### Fixed

- Apply staged, strictly shrinking pair-safe fallback attempts after an explicit
  upstream `response_failed`, including failures whose original request is
  already below the ordinary compaction ceiling. Each fallback retains the
  latest user context and complete tool call/output pairs.
- Preserve a compacted request during a pre-content SSE reconnect instead of
  reopening the original rejected replay body.

### Verified

- Added regression coverage for sub-budget failures, impossible target budgets,
  staged reduction, pair integrity, latest-user retention, and fallback-only
  cache-key removal.

## [1.0.7] - 2026-07-14

### Fixed

- When an upstream gateway explicitly returns HTTP 400 with a Responses
  `response_failed` execution error, make up to three strictly shrinking adaptive fallbacks for replay context: remove
  only the oldest contiguous input prefix, preserve the latest user context and
  complete tool call/output pairs, and remove the stale `prompt_cache_key` only
  from fallback requests. Ordinary client-side 400 errors
  remain non-retryable.

### Verified

- Added regression coverage for pair integrity, latest-user retention,
  fallback-only cache-key removal, no-safe-suffix behavior, and unrelated HTTP
  400 rejections.

## [1.0.6] - 2026-07-14

### Fixed

- Treat upstream HTTP 524 gateway timeouts as bounded, transient failures,
  alongside 429 and 5xx responses.

## [1.0.5] - 2026-07-14

### Fixed

- Formalized original-conversation recovery boundaries: lifecycle operations do
  not require a new conversation, a forced client quit, or session mutation.
- Kept AIGW as the sole owner of marked provider configuration; the proxy owns
  only the data-plane adapter and its local process lifecycle.

## [1.0.4] - 2026-07-14

### Added

- Added a manifest for the installed runtime payload and a narrowly scoped
  listener reload that verifies replacement by the watchdog.

## [1.0.3] - 2026-07-14

### Fixed

- Preserved required `agent_message` encrypted-content blocks while removing
  only replayed reasoning state. This fixes rejected payloads missing the
  required `encrypted_content` field.

## [1.0.2] - 2026-07-14

### Fixed

- Removed only non-replayable local image references at the outbound boundary.
- Preserved custom Windows service parameters across logon.
- Added reversible route control, strict route-drift handling, and AIGW route
  delegation through AIGW's public CLI.

## [1.0.1] - 2026-07-08

### Fixed

- Allowed installation to complete on minimal Linux environments that lack a
  user systemd bus and cron; the required manual persistence step is explicit.

## [1.0.0] - 2026-07-08

### Added

- Introduced the portable loopback Responses compatibility adapter, watchdog,
  platform service adapters, bounded upstream retries, and SSE reconnect
  handling.
