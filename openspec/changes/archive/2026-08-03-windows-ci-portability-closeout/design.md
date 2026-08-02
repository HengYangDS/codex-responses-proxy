## Context

See [proposal.md](proposal.md). The Windows runner currently spends roughly
eleven minutes in the real handoff suite because `pids_naming_path()` obtains one
complete process inventory and then re-queries every PID through PowerShell.
The same hosted run also proves that a test-only literal slash is not portable.

## Goals / Non-Goals

**Goals:**

- Keep one host inventory query per `pids_naming_path()` call on Windows and
  Linux.
- Preserve Darwin native `kern.procargs2` identity for paths containing spaces.
- Preserve fail-closed per-PID identity revalidation immediately before signal.
- Keep launchd rendering assertions native to the executing test host.

**Non-Goals:**

- Weakening exact process ownership.
- Caching inventory across calls or persisting host process state.
- Changing route backpressure, HTTP semantics, release identity, or timeouts.
- Raising CI timeouts to hide repeated host queries.

## Decisions

### Inventory commands are evidence on non-Darwin hosts

`_process_inventory()` already returns each PID with its command line. On Linux
and Windows, `pids_naming_path()` will validate that captured command directly.
Darwin remains the exception because `ps` loses argv boundaries; it will
continue to re-read each candidate with native `sysctl`.

### Signal-time proof remains live

Discovery is only a candidate list. `terminate_pid()` and listener ownership
continue to call `pid_names_path()` immediately before mutation, so the
performance repair does not convert stale inventory into termination authority.

### Tests prove query count, not elapsed time

A focused test will require one inventory call and zero per-PID command queries
on non-Darwin platforms. This is deterministic and directly proves the removed
O(process-count) boundary without relying on runner speed.

## Risks / Trade-offs

- **A process can change after inventory** -> discovery never authorizes a
  signal; mutation paths retain live PID identity revalidation.
- **Platform mocking can accidentally invoke native APIs** -> only the Darwin
  branch uses native argv and existing synthetic contracts cover it.
