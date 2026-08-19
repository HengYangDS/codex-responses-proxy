## Context

`service_id` deliberately normalizes with the host path implementation. A fixture that patches only the home string but not the path flavor creates an impossible hybrid filesystem.

## Decision

Build the canonical fixture through `default_data_dir` and derive alternate sibling roots from that value. The test now exercises one coherent host filesystem model on macOS, Linux, and Windows.

## Non-goals

- no change to service identity calculation;
- no platform exception, skip, timeout, or compatibility branch;
- no production-service or listener mutation.
