# Close Windows native process ownership

## Why

The v2.0.22 Windows native tests proved every handoff behavior, then failed
while deleting the temporary bundle because its successor still mapped a
native module. A PID plus a later argv lookup is not durable ownership: Windows
may deny that lookup during exit, so teardown can miss the process it already
proved healthy.

## What changes

- capture the successor PID, executable identity, and creation time at the
  successful health observation;
- terminate only that captured PID generation during teardown;
- reject PID reuse and remove the payload only after every captured generation
  is absent;
- publish the forward-only repair as v2.0.23.

## Non-goals

- no longer cleanup delay or retry-only workaround;
- no provider, replay, backpressure, or runtime handoff protocol change;
- no rewrite of v2.0.22 tags, runs, Releases, or assets.
