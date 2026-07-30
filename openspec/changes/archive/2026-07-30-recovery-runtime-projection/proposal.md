## Why

During a protocol-v2 cross-version handoff, the old listener freezes its loaded
serving identity but reads the manifest digest from the newly committed disk
projection. Recovery incorrectly required that digest to identify the rollback
projection, so a real preserved transaction could not be restored.

## What Changes

- Bind the live listener's release, serving digest, and receipt to the rollback
  projection.
- Bind its reported manifest digest to the committed candidate projection that
  is actually on disk.
- Keep the existing single-listener, accepting, idle, publication, and snapshot
  integrity checks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: subject=preserved cross-version recovery; reuse=extend;
  change=modify; facet:lifecycle=installation,recovery;
  facet:surface=runtime,transaction,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Weakening publication, process ownership, snapshot integrity, or idle-listener
  requirements.
- Treating a committed candidate projection as a completed installation.
- Changing Codex transcript, session, model metadata, or AIGW configuration.

## Impact

The source-side recovery transaction, its adversarial tests, runtime-upgrade
specification, and release metadata change together. Normal request processing
and provider routing do not.
