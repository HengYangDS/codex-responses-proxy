## Why

The repository must describe and implement one terminal product rather than
carry multiple installation models, repeated policy projections, or release
workflow coupling. The accepted product is a self-contained native Responses
gateway with exact lifecycle ownership and independent distribution planes.

## What Changes

- Reduce installation, rollback, recovery, purge, tests, and documentation to
  one current native payload contract.
- Make every supported supervision adapter discoverable and black-box test
  actual platform selection in the built executable.
- Keep expected product failures concise, actionable, and free of traceback,
  warning, module, or private-path leakage.
- Derive tool and matrix projections from repository-owned sources instead of
  repeating versions in tests or CI.
- Keep GitLab and GitHub release workflows independent while deriving their
  product identity and toolchain inputs from repository-owned sources.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: one complete executable, bounded UX, and repository-owned DX.
- `runtime-upgrade`: one current payload, exact handoff, rollback, recovery, and purge.

## Impact

The CLI, native executable, lifecycle, tests, dependency lock, cross-platform
CI contracts, and documentation change. Publication, installation, live
provider acceptance, original-session continuity, and lane retirement remain
post-land lifecycle operations. Codex JSONL, SQLite, messages, stored items,
model metadata, IDE products, and client configuration remain untouched.
