## Context

Release 2.0.4 contains the fail-closed projector that preserves only the
payload-free `compaction_trigger`. Its focused request test proves the item
shape, while the existing route test proves equivalent provider-portable
projection for ordinary dialogue across `dmxapi`, `ucloud`, and `aihubmix`.
Those proofs do not directly compose the remote-compaction item with the three
route namespaces.

## Goals / Non-Goals

**Goals:**

- Compose the released remote-compaction control with the existing exact
  three-route contract.
- Remove Azure from the live canonical provider name because the governed
  namespace and manifest entry are UCloud.
- Keep unknown future replay items fail-closed before upstream I/O.
- Keep source, installation, AIGW projection, and same-session acceptance as
  distinct evidence planes.

**Non-Goals:**

- Reimplementing the 2.0.4 projector.
- Generalizing arbitrary compaction item types.
- Rewriting consumer or conversation state.
- Treating a local route fixture as proof of a provider's live service.

## Decisions

### 1. Extend the common route fixture instead of adding provider branches

The existing test already sends one request through all three namespaces and
captures the exact forwarded bytes. Adding `compaction_trigger` to that body
proves the shared projection and route dispatch together without duplicating
production behavior.

### 2. Assert equality of all three forwarded bodies

Each captured request must contain the exact payload-free trigger, and all
three serialized bodies must be byte-identical. This directly excludes
route-specific replay mutation.

### 3. Preserve the existing fail-closed test

`future_item` remains a local 400 with no upstream request. The new positive
coverage does not weaken the default-deny grammar.

### 4. Historical evidence remains immutable

Archived OpenSpec changes and old evidence may retain the terminology used at
their creation. Only the current canonical spec is corrected.

## Risks / Trade-offs

- The route fixture proves proxy behavior, not third-party availability or
  quota. Live provider claims remain separately bounded.
- UCloud unchanged-session recovery and each fresh AIGW probe are distinct live
  evidence. DMXAPI remains local-only until quota is restored.

## Migration Plan

1. Add the route-level compaction regression and prove it passes on the current
   source candidate.
2. Correct current canonical provider naming and validate OpenSpec strictly.
3. Run focused and complete source proof, then archive and land through ETHOS.
4. Verify AIHubMix through AIGW and retain UCloud as the restored active route.
5. Verify DMXAPI projection/route locally without claiming upstream success.

Rollback reverts this documentation-and-regression increment; it never changes
the already installed 2.0.4 runtime or any Codex session record.
