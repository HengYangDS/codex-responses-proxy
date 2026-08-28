## Why

A published-predecessor Linux upgrade can transfer listener ownership to the
successor while leaving the native supervisor bound to the predecessor. The
existing lifecycle ordered supervisor replacement before listener handoff and
then tried to compensate after transaction closure, creating competing state
authorities and making recovery depend on timing rather than proved ownership.

The lifecycle must make one authority responsible at each phase and keep the
transaction open until both the terminal listener and its native supervisor are
proved. This change removes the compensating path instead of extending it with
more timeouts, retries, or platform exceptions.

## What Changes

- Reorder upgrade convergence to materialize and activate the successor,
  transfer listener ownership, prove the terminal admission owner, bind and
  prove the native supervisor, then prune and close the transaction.
- Make the transaction journal the sole recovery authority during deployment
  and the active-generation selector the sole steady-state authority.
- Treat launchd, systemd, and Task Scheduler as derived projections; none may
  independently select the serving payload.
- Preserve candidate and rollback bytes when supervisor proof fails after a
  successful handoff, enabling idempotent recovery without replaying handoff.
- Remove the post-closure supervisor compensation path and predecessor-specific
  special cases.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: require terminal listener ownership before native
  supervisor rebinding, and require supervisor identity proof before transaction
  closure or obsolete-generation pruning.

## Impact

The change affects transactional deployment, recovery, native supervision, and
lifecycle tests. It does not change request transformation, provider routing,
credentials, client configuration, release publication, or conversation state.
Linux/systemd-user is the first real-host acceptance target; macOS and Windows
remain unproved until equivalent native receipts exist.
