# Changelog

This project follows [Semantic Versioning](https://semver.org/). The changelog
records released, user-relevant behavior only. `Unreleased` is reserved for
work that has not yet been tagged.

## [Unreleased]

## [1.0.10] - 2026-07-17

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
