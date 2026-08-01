## Context

`runtime/state.py` mixed four independent reasons to change. Replay returned a
tuple whose second element was both human-readable text and an implicit metrics
protocol. The Forge documentation also alternated between identical commit
graphs and provider-specific identities, which cannot both be true when each
Forge requires a different author email and signature.

## Decisions

### Runtime state follows semantic ownership

`runtime/admission.py` owns request and handler admission plus drain leases.
`runtime/telemetry.py` owns secret-free counters and status projection.
`runtime/logging.py` owns bounded redaction, path labels, exception labels, and
log rotation. `transport/cooldown.py` owns a bounded provider-neutral cooldown
cache. Callers import these owners directly; no `state` facade remains.

### Replay returns data, not prose

`ProjectionResult` carries the optional request body, status, rejection reason,
and immutable `ProjectionMetrics`. Diagnostics are derived at the logging or
HTTP projection edge. Telemetry receives integer fields directly and never
parses diagnostic text.

### Forge parity is correspondence, not object identity

GitLab and GitHub use their required provider-native emails and trusted
signatures. Their commit object ids therefore differ. The publication contract
proves tree, message, date, and parent-topology correspondence and forbids
destructive history updates; it does not claim one identical commit graph.

## Non-Goals

- Change provider-specific wire policy or runtime configuration.
- Add a compatibility wrapper for removed internal APIs.
- Edit Codex JSONL, SQLite, transcripts, response-item data, or model metadata.

## Rollback

Revert the atomic source commit before publication. Do not restore only the old
facade or string protocol because either would recreate multiple authorities.
