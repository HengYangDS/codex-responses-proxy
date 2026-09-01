## Context

See [proposal.md](proposal.md). The product requires raw byte and SSE
preservation, explicit trust roots, bounded recovery, and one frozen native
executable on each supported platform. The discriminating contract is a total
SSE deadline whose next blocking read is shortened to the remaining budget.

## Goals / Non-Goals

**Goals:**

- Correct the dependency decision using executable evidence rather than API
  appearance or popularity.
- Preserve the current deadline guarantee without adding an unused dependency
  or parallel transport.
- Keep a reusable acceptance bar for future transport candidates.

**Non-Goals:**

- Change runtime code, provider routes, recovery policy, response projection,
  or CLI surface.
- Preserve a speculative migration merely because it was previously recorded.

## Decisions

1. **Reject the current HTTPX migration.** In HTTPX 0.28.1, changing the request
   timeout extension after raw iteration starts does not change the timeout used
   by the active HTTP/1.1 response-body iterator. A loopback probe changed the
   read budget from 2.0 seconds to 0.1 seconds after the first chunk; the next
   read still blocked for approximately 0.5 seconds until the server replied.
2. **Do not compensate with private internals or worker cancellation.** Reaching
   into HTTPCore recreates the same private coupling; a reader thread or async
   rewrite adds cancellation, ownership, shutdown, and frozen-runtime surface
   without proven net simplification.
3. **Retain one current transport temporarily.** Existing `urllib` remains the
   sole upstream owner because it satisfies the current behavior and release
   evidence. Retention is not endorsement: private traversal remains a named
   design liability with an explicit replacement bar.
4. **Require semantic replacement.** A future candidate must demonstrate public
   dynamic read-budget control, raw undecoded bytes, direct proxy isolation,
   provider recovery parity, native-platform packaging, and deletion of more
   owned complexity than it adds before selection.

## Risks / Trade-offs

- **The current transport retains private socket traversal** -> keep the defect
  explicit and bounded; revisit only with a candidate that removes it without a
  larger lifecycle surface.
- **Rejecting HTTPX here can be mistaken for rejecting mature tools generally**
  -> the decision remains semantic: adopt mature tools when they replace the
  hard responsibility, not when they only wrap it.

## Migration Plan

1. Record the focused HTTPX 0.28.1 timeout result and amend DR-0006.
2. Confirm no HTTPX dependency, adapter, fallback, or product-code residue was
   introduced.
3. Validate documentation and archive this no-behavior Change.
