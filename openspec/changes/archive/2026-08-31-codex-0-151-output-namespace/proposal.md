## Why

Codex 0.151.0 includes optional `namespace` metadata on a valid
`function_call_output`. The proxy currently rejects that documented client
shape before upstream I/O even though the metadata is not needed by the
provider-portable call/output pair.

## What Changes

- Admit optional `namespace` metadata on a correctly paired function-call
  output.
- Remove that metadata from the outbound provider-portable projection while
  preserving the verified call kind, `call_id`, and visible output.
- Continue rejecting every unproved output field and every orphaned,
  mismatched, or duplicate output.
- Assign the immutable patch release identity `3.1.9` to the corrected product.

## Capabilities

### Modified Capabilities

- `provider-portable-responses`: Accept the documented Codex namespaced
  function-output shape without weakening fail-closed replay admission.

## Impact

The change is limited to the Responses request projector, its focused protocol
tests, release identity, Changelog, and this official Change. It adds no
dependency, compatibility state, provider branch, client configuration, or
persisted runtime surface.
