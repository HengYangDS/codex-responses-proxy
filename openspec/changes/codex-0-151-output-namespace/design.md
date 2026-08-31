## Context

See [proposal.md](proposal.md). Codex 0.151.0's public protocol model permits an
optional `namespace` field on `function_call_output`. The proxy already
validates the output against its matching function call and reconstructs the
provider-portable form from `call_id` and visible output.

## Goals / Non-Goals

- Admit the one documented metadata field without weakening unknown-field
  rejection.
- Preserve the existing call/output relationship and outbound normal form.
- Do not add version branches, provider branches, migration state, or request
  logging.

## Decisions

### Extend the existing output grammar, not the transport

Add `namespace` to the existing bounded input-field set. The projector will
continue constructing the outbound item from its semantic fields, so the
namespace is intentionally discarded. This is preferable to forwarding all
recognized input fields or adding a Codex-version adapter: both would enlarge
the provider boundary without adding product value.

### Keep exact unknown-field rejection

The regression will also prove that an unrelated field remains rejected. This
keeps the fail-closed contract observable without adding a second validator.

## Risks / Trade-offs

- **Risk:** A future Codex release adds another legitimate field. **Mitigation:**
  retain the stable reason code and compare each new client shape with its
  versioned public protocol before changing the grammar.

## Migration Plan

Release and install the corrected proxy through the existing transactional
lifecycle as `3.1.9`. Roll back to 3.1.8 if installed acceptance fails.
