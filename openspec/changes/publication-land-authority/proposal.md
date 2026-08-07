## Why

The completed publication-topology Change proved local readiness, but its
Commitment omitted the candidate-ref compare-and-swap permission required by
the governed landing operation. Proof therefore passed while landing correctly
failed closed.

## What Changes

- Declare candidate landing as the only new authority.
- Preserve the already accepted product and publication semantics unchanged.
- Prove, archive, and land this forward fix through the normal lifecycle.

## Non-goals

- No product-source, runtime, provider, Forge, credential, or session mutation.
- No compatibility path or second lifecycle mechanism.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: require a completed publication Change to carry the
  minimal permission needed for governed candidate integration.
