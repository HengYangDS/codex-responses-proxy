## Why

The failed 2.0.12 hosted matrix exposed three product portability defects and
one CI-noise defect that local macOS proof could not detect. Version 2.0.13 must
repair those exact failures without weakening identity, coverage, or release
evidence.

## What Changes

- Detect listener ownership without requiring an unbundled host command.
- Preserve the listener-owned handoff transaction after READY even when the
  requesting controller disconnects before receiving the acknowledgement.
- Verify Git executable intent from the index rather than host filesystem mode.
- Configure locked dependency installation without Windows hardlink warnings.
- Publish only as the forward 2.0.13 release; retain failed 2.0.12 evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: require dependency-complete native execution, host-neutral
  Git metadata checks, clean CI output, and disconnect-safe handoff acceptance.
- `product-interface`: require the native executable to carry its process
  inspection capability instead of depending on optional host tools.

## Impact

The product dependency graph, process supervision, handoff HTTP projection,
repository tests, CI environment, release metadata, and their specifications
change. Provider request behavior, AIGW, Codex history, JSONL, SQLite, model
metadata, and the currently installed runtime remain untouched until a verified
2.0.13 asset is ready for transactional reload.
