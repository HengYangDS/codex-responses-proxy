## Why

The executable exposes release identity only as a `version` subcommand, while
users and packaging tools conventionally probe `--version`. Keeping both would
create parallel public semantics, so the command grammar should have one
unambiguous version surface.

## What Changes

- Expose release identity through top-level `--version`.
- **BREAKING** Remove the redundant `version` subcommand and release the
  narrowed grammar as `3.0.0`.
- Exercise the same option in wheel and native-release verification.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: Narrow the public grammar to one conventional version surface.

## Impact

The public CLI grammar, native prewarm probe, release verification, tests,
changelog, and product-interface specification change. Runtime lifecycle and
wire behavior are unchanged.
