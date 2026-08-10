## Why

The canonical evidence-layout specification still carries OpenSpec's generated
`TBD` purpose after archive. That placeholder is not product truth and weakens
the terminal documentation contract.

## What Changes

- Replace the generated placeholder with the current evidence-layout purpose.
- Preserve the existing evidence ownership and Forge-parity requirements.

## Capabilities

### Modified Capabilities

- `evidence-layout`: state the current project-owned purpose directly.

## Impact

Documentation authority only. Claims and chronicles remain the only durable
evidence roots, Forge parity remains owned by `tools/forge/audit.py`, and no
runtime, release, compatibility, migration, or evidence-carrier behavior changes.
