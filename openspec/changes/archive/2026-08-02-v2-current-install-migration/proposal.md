## Why

The live v2.0.0 installation is valid and digest-verified, but the v2.0.3
installer classifies its 57-file schema-2 manifest as an unsupported retired
layout. The upgrade therefore fails before payload mutation. Separately, the
runtime remains port-configurable but its sole default is still the retired
8791 compatibility port rather than the active 8792 service.

## What Changes

- Admit the exact v2.0.0 protocol-v2 runtime inventory as a supported prior
  projection, including its canonical release receipt, deployments where the
  optional finalized install-state file is absent, and rollback-safe retirement
  of `replay/event.py`.
- Make 8792 the single listener default while preserving installer, control,
  uninstall, and environment overrides.
- Reject production port literals outside the one runtime configuration owner.

## Capabilities

### Modified Capabilities

- `runtime-upgrade`: subject=installed runtime migration and listener port;
  reuse=extend; change=modify; requires exact prior-inventory proof and one
  configurable 8792 default; facet:lifecycle=installation,rollback,operation;
  facet:surface=runtime,test,openspec; facet:authority=source,test,openspec

## Out of Scope

- Editing Codex session JSONL, SQLite, transcripts, or model metadata.
- Reintroducing the retired 8791 compatibility service.
- Accepting arbitrary historical manifests or unverified installed files.

## Impact

Runtime configuration, exact historical projection verification, rollback
inventory, focused tests, release metadata, and operator documentation change.
