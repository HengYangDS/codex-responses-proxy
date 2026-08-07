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
- Publish one final forward release independently to GitLab and GitHub from the
  same accepted source and asset bytes.
- Install that release, verify DMXAPI, UCloud, and AIHubMix with `store=false`,
  prove the original Codex conversation can continue, and retire all owner
  lanes and temporary runtime state.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: one complete executable, bounded UX, and repository-owned DX.
- `runtime-upgrade`: one current payload, exact handoff, rollback, recovery, and purge.

## Impact

The CLI, native executable, lifecycle, tests, dependency lock, cross-platform
CI, release evidence, documentation, and repository-family state change. Codex
JSONL, SQLite, messages, stored items, model metadata, IDE products, and client
configuration remain untouched.
