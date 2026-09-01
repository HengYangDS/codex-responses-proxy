## Context

See [proposal.md](proposal.md). The diagnostic path currently owns a broad
known-item set while the projection path independently encodes a smaller set of
branches. Both are valid locally, but their combination admits contradictory
classification.

## Goals / Non-Goals

**Goals:**

- Give each supported input item one classification and one projection strategy.
- Make unknown and recognized-but-unimplemented states distinct and fail closed.
- Derive diagnostics and projection dispatch from the same immutable policy.
- Preserve call/output integrity when removing Codex-local shell history that a
  third-party provider cannot consume.

**Non-Goals:**

- Broaden provider-specific behavior or infer portable semantics.
- Add a protocol framework, registry layer, fallback, or compatibility shim.
- Inspect or mutate Codex conversation storage.

## Decisions

1. **Use one immutable, typed module-level policy.** A small enum and frozen
   value record are sufficient because the policy is static, local, and pure.
   A validation framework would add runtime and maintenance surface without
   removing another owner.
2. **Name strategies, not handlers.** The policy describes semantic categories;
   the request projector remains the sole owner of transformation functions.
   This avoids a second dispatch framework while making coverage exhaustive.
3. **Reject recognized gaps as `schema_drift`.** This preserves fail-closed
   behavior while distinguishing product lag from genuinely unknown input.
4. **Drop local shell history only as a validated pair.** The projector validates
   the Codex-local call shape, registers its `call_id`, requires the matching
   `function_call_output`, then removes both. An orphan, duplicate, or mismatched
   output remains a local rejection.
5. **Test closure rather than duplicate inventories.** Contract tests enumerate
   the public policy and prove every strategy has diagnostic and projection
   behavior; tests do not maintain another item list.

## Risks / Trade-offs

- **Policy and projector can drift if a strategy is added incompletely** → an
  exhaustive contract test fails before release.
- **Recognized schema drift remains unavailable until modeled** → the explicit
  local rejection is safer than silent deletion or provider-dependent replay.
