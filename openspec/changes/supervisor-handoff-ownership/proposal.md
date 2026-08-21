## Why

The `2.0.53` release candidate exposed a cross-platform ownership defect: the
handoff child restarted its own native supervisor while it was becoming the
listener, so Linux and Windows could terminate the successor before the
transaction finalized. Native supervision must be committed and proved by the
installer before listener capability transfer begins.

## What Changes

- Move native-supervisor rebinding into the payload deployment transaction.
- Require the installer to prove the supervisor declares the committed
  successor before requesting handoff.
- Remove native-service mutation from the handoff child and delete the unused
  finalization callback surface.
- Restore predecessor payload and supervision when a pre-handoff rebind or
  handoff fails; retain recovery state only when the listener outcome is
  genuinely unknown.
- Validate the repair through the Python matrix and native macOS, Linux, and
  hosted Windows product flows.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: assign native supervision to the installer transaction and
  restrict the handoff child to listener transfer and runtime identity.

## Impact

The deployment orchestrator, native-service boundary, handoff child, release
acceptance tests, runtime-upgrade specification, lifecycle documentation, and
failed `2.0.53` release candidate are affected. Provider routing, credentials,
client configuration, Codex state, and the handoff wire protocol do not change.
