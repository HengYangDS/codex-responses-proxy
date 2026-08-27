## Why

The 3.1.1 native Windows acceptance repeatedly timed out during `reload` after
installation, health checks, and a real Responses request had succeeded. The
regression began when controller completion made `psutil` TCP-owner projection
authoritative. Windows socket sharing does not guarantee that this projection
will move from the predecessor PID to the successor PID, even after the
protocol has finalized and the predecessor process has exited.

## What Changes

- Store each admitted payload in an immutable generation below one stable
  control root. Select the active generation and its sole predecessor through
  one atomic selector instead of overwriting a running payload in place.
- Prove handoff convergence with the exact captured predecessor generation,
  exact captured successor generation, and finalized runtime identity.
- Require the predecessor generation to exit before success, without treating
  platform-specific TCP attribution as lifecycle authority.
- Make upgrade, reload, rollback, recovery, uninstall, command projection, and
  native supervision resolve the same selected-generation model.
- Use a transaction-owned snapshot only to migrate a verified legacy
  single-directory installation; it is not a retained rollback authority.
- Retain listener discovery as the admission proof before handoff begins.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: define portable completion as successor finalization plus
  predecessor-generation exit, following exact listener admission.

## Impact

The change replaces in-place native payload mutation with immutable generation
selection across the lifecycle implementation, tests, documentation, and
runtime-upgrade specification. It adds no dependency, provider behavior,
client projection, or formal-runtime mutation during source verification. The
legacy migration boundary is deliberately one-way; the terminal product model
contains no second rollback store or compatibility state machine.
