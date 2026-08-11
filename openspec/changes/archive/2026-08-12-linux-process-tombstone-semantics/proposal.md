# Linux process tombstone semantics

## Why

Native handoff teardown currently equates a retained PID record with a live
process. In a Linux container whose PID 1 does not reap adopted children, an
already-exited successor remains observable as a zombie. `psutil.wait()` cannot
reap that non-child, so teardown reports a false orphan after successful exit.

## What changes

- Define an owned process generation as live only while it can still execute.
- Treat an exact-generation zombie as exited, without treating PID reuse or an
  inaccessible running process as success.
- Cover both observation and bounded termination with focused regressions.

## Non-goals

- Do not weaken executable identity checks or orphan detection.
- Do not change handoff topology, signals, process groups, or production ports.
- Do not special-case CI providers.
