# Changelog

This project follows [Semantic Versioning](https://semver.org/). The changelog
records released, user-relevant behavior only. `Unreleased` is reserved for
work that has not yet been tagged.

## [Unreleased]

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
- Record the proxy source SHA-256 captured when the listener loaded the payload,
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
