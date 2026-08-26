## Why

The 3.1.1 native Windows acceptance repeatedly timed out during `reload` after
installation, health checks, and a real Responses request had succeeded. The
regression began when controller completion made `psutil` TCP-owner projection
authoritative. Windows socket sharing does not guarantee that this projection
will move from the predecessor PID to the successor PID, even after the
protocol has finalized and the predecessor process has exited.

## What Changes

- Prove handoff convergence with the exact captured predecessor generation,
  exact captured successor generation, and finalized runtime identity.
- Require the predecessor generation to exit before success, without treating
  platform-specific TCP attribution as lifecycle authority.
- Apply the same completion proof to ordinary reload, upgrade, rollback, and
  controller-failure recovery.
- Retain listener discovery as the admission proof before handoff begins.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: define portable completion as successor finalization plus
  predecessor-generation exit, following exact listener admission.

## Impact

The change is confined to native handoff proof and its tests. It adds no state
machine, dependency, compatibility path, provider behavior, client projection,
or formal-runtime mutation during source verification.
