# Design

## One durable process identity

At the health proof point, the fixture resolves the expected executable and
captures `pid + create_time`. The executable path proves ownership once; the
creation time then distinguishes that process generation from later PID reuse.
Teardown no longer depends on argv remaining readable during process exit.

## Ordered teardown

Teardown captures any additional exact-executable processes found by inventory,
terminates every captured generation, and verifies all are absent before
removing the bundle. A bounded `PermissionError` retry remains only for the
short delay between confirmed process exit and Windows releasing mapped files.

## Rejected alternatives

- **Increase the deletion timeout:** hides the ownership leak and remains
  timing-dependent.
- **Signal a retained PID without creation time:** can terminate an unrelated
  process after PID reuse.
- **Require a second argv read:** recreates the Windows denial that caused the
  failure.
