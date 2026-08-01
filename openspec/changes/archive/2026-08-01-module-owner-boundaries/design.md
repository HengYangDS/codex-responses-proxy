## Context

`projection` owned installed-manifest semantics but also exposed private file
primitives used by candidate, migration, rollback, state, and transaction.
`transaction` then re-exported state, inventory, and digest symbols. Moving the
files into a package had not created truthful module boundaries.

## Decisions

### Owned payload bytes have one filesystem owner

`payload/owned_files.py` owns canonical relative paths, symlink-safe regular
file lookup, atomic writes, canonical JSON reads, and the complete owned-file
inventory. It does not own manifests, transactions, rollback, or release state.

### Consumers import the defining module

State paths come from `payload.state`; digests from `payload.digest`; inventory
from `payload.inventory`; manifest semantics from `payload.projection`.
`payload.transaction` keeps only transaction orchestration and recovery.

### Architecture checks reject fake splits

The owner-boundary test parses payload modules and rejects peer-module private
attribute access and alias-only forwarding assignments. The gate has no growing
allowlist for retired transaction aliases.

## Non-Goals

- Split runtime admission, telemetry, logging, or provider cooldown.
- Change provider replay or transport behavior.
- Add compatibility wrappers for removed internal aliases.

## Rollback

Revert this atomic change. Do not restore only the forwarding aliases because
that would recreate two authorities without restoring the old implementation.
