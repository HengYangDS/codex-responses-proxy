# Changelog

This project follows [Semantic Versioning](https://semver.org/). The changelog
records released, user-relevant behavior only. `Unreleased` is reserved for
work that has not yet been tagged.

## [Unreleased]

## [1.0.7] - 2026-07-14

### Fixed

- When an upstream gateway explicitly returns HTTP 400 with a Responses
  `response_failed` execution error, make one adaptive fallback for oversized
  replay context: remove only the oldest contiguous input prefix, preserve the
  latest user context and complete tool call/output pairs, and remove the stale
  `prompt_cache_key` only from the fallback. Ordinary client-side 400 errors
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
