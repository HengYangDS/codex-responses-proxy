## Context

See [proposal.md](proposal.md). The process currently owns one global bounded
semaphore and checks provider cooldown only before global admission. That order
cannot protect requests already waiting behind another request from the same
provider once the leading request establishes a cooldown.

## Goals / Non-Goals

**Goals:**

- Keep the existing process-wide capacity bound and drain accounting.
- Add exactly one process-local slot per provider route.
- Release global and route slots on every terminal path.
- Make the post-queue cooldown decision before any upstream call.

**Non-Goals:**

- Provider-specific branches or hard-coded provider names.
- Distributed rate limiting or provider quota discovery.
- A second admission subsystem or compatibility facade.

## Decisions

### Admission owns both capacity dimensions

`runtime.admission` remains the single owner of active-response accounting. A
successful Responses admission acquires the existing global slot and a route
slot keyed by the registry route name. This keeps drain, timeout, release, and
test reset semantics cohesive. Moving route locks into provider modules was
rejected because it would duplicate lifecycle behavior and make each new
provider implement concurrency mechanics.

### Route slots are single-flight and lazy

The process creates one bounded semaphore per observed route under the existing
admission lock. The route name is data from the provider registry, not a fixed
list. Different route semaphores can therefore proceed concurrently while the
global semaphore still bounds total work. A global limit of one remains a safe
deployment-only containment setting until 2.0.6 is installed.

### Cooldown is checked on both sides of queuing

The early cooldown check keeps already-cooled requests out of admission. After
acquiring a route slot, Responses transport checks the same cooldown owner
again. If the preceding request established a cooldown while this request was
queued, the queued request receives the existing local HTTP 429 without an
upstream call, then releases its slots normally.

### HTTP 429 remains terminal

The wire path still performs exactly one upstream attempt, relays eligible
headers and body, and records a bounded provider-scoped cooldown. This change
does not add retry, sleep, or speculative fallback behavior.

## Risks / Trade-offs

- **One long request delays the same provider route** → queue timeout remains
  bounded and explicit; unrelated routes retain concurrency.
- **Route entries remain for the process lifetime** → the provider registry is
  a bounded configured set, and test reset clears the map.
- **A cooldown can start while a request waits** → the post-queue check rejects
  it locally, which is the intended protection rather than wasted remote I/O.

## Migration Plan

1. Prove RED for same-route overlap, cross-route concurrency, and cooldown
   beginning while a request waits.
2. Implement the minimal admission and transport changes, then prove focused
   GREEN and the full Python 3.12-3.14 quality matrix.
3. Forward-fix the known Linux CI test-platform issue, prepare signed 2.0.6,
   and preserve failed 2.0.5 tags and runs.
4. Publish independently to GitLab and GitHub, verify asset identity, and use
   the existing transactional installation protocol.
5. Verify live providers and the unchanged original Codex task. Rollback uses
   the preceding signed release and never edits conversation state.
