# Exact rollback for native upgrades

## Why

A failed native upgrade can introduce bundle members that did not exist in the
previous release. Restoring only the prior manifest inventory leaves those
candidate-only files behind, so disk state is no longer the exact prior payload.

## What changes

- Bind rollback cleanup to the verified candidate inventory.
- Restore every retained prior byte.
- Remove only candidate paths that were absent from the prior snapshot.
- Preserve unknown, non-candidate install content.
- Refresh the exact development lock to the current stable toolchain before release.

## Non-goals

- No change to request routing, provider behavior, or Codex session storage.
- No process termination outside the rolling-handoff protocol.
