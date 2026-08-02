## Context

Codex Responses Proxy already relays an upstream HTTP 429 after one upstream
attempt and records a bounded provider-scoped deadline. The cache is shared by
the rate-limit path and the DMX wire-failure path. Its current replacement
assignment is safe for first insertion but not for overlapping failures: a
later shorter duration replaces a still-active longer deadline.

## Goals / Non-Goals

**Goals:**

- Make cooldown deadline updates monotonic for the same key.
- Preserve bounded memory and expiry semantics.
- Prove the exact 300-second then five-second overlap case.
- Carry the original failed thread through unchanged post-installation
  acceptance.

**Non-Goals:**

- Persisting cooldowns across process restarts.
- Combining cooldown state across providers or request fingerprints.
- Changing `Retry-After` parsing or downstream response behavior.
- Mutating Codex session storage.

## Decisions

### 1. The deadline owner keeps the maximum active deadline

Under the existing lock, `remember_failure` compares the stored deadline with
the new `moment + cooldown_seconds` deadline and stores the later value. Expired
entries are purged first, so this does not resurrect expired state.

### 2. Capacity remains bounded

Eviction still sorts the resulting deadline map and drops the earliest
deadlines when capacity is exceeded. No request payload or provider response is
retained.

### 3. Completion remains multi-plane

Focused RED/GREEN and full source proof establish a candidate only. Publication,
transactional installation, listener identity, and unchanged-thread recovery
remain separate evidence planes.

## Risks / Trade-offs

- A longer valid cooldown can outlive a later shorter provider hint. This is the
  conservative interpretation: the proxy must not resume before the strongest
  still-active instruction expires.
- The rule also applies to the shared request-fingerprint cooldown cache. That
  prevents a repeated failure from shortening an already active protection and
  preserves isolation by key.

## Migration Plan

1. Prove RED for a 300-second deadline followed by a five-second deadline.
2. Store the maximum active deadline under the existing lock and prove GREEN.
3. Run focused tests, strict OpenSpec, release metadata checks, Python
   3.12-3.14 behavior tests, and HEAD-bound ETHOS proof.
4. Land only the narrow increment after the active signed release train; install
   through the existing protocol-v2 transaction when each listener is idle.
5. Resume the unchanged failed thread and verify multiple successful turns.

Rollback uses the preceding signed release and never edits Codex session state.
