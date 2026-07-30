# Recovery Runtime Projection

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
