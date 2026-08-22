## Why

The published `2.0.57` asset cannot upgrade an installed `2.0.56` runtime.
The invoked `2.0.56` installer writes the runtime carrier with its own schema,
then the `2.0.57` successor rejects that carrier before handoff. Conversely,
the unusable `2.0.57` installer writes its incompatible schema for every later
candidate. The upgrade rolls back safely, but `2.0.57` cannot be retained as a
supported predecessor.

## What Changes

- Keep `runtime-config.json` on the established stable schema used by the
  released predecessor.
- Keep macOS service ownership in the live installation context instead of
  expanding the persisted product carrier with an operating-system home path.
- Prove that a carrier written by the released predecessor activates the
  successor and retains exact macOS plist ownership.
- Retire `2.0.57` as a failed intermediate release and prove `2.0.58` directly
  from the last usable published predecessor, `2.0.56`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: Require the installer generation and successor payload to
  share one stable runtime-carrier contract.

## Impact

Runtime carrier serialization, successor activation, macOS service projection,
published-predecessor compatibility, and the successor release are affected.
Provider routing, credentials, Codex state, AIGW, and the installed `8792`
service are not modified during source development.
