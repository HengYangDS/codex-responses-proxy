## Why

The locked runtime and verification graph contains superseded stable releases.
Refreshing that graph now removes avoidable diagnostic and maintenance drift
without changing the proxy contract.

## What Changes

- Refresh Cyclopts, Nox, ty, and PyInstaller to their reviewed stable releases.
- Regenerate the sole dependency lock from the declared project metadata.
- Verify the refreshed graph through the existing complete command surface.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change updates tooling and dependencies only; public behavior and
lifecycle semantics do not change.

## Impact

Only `pyproject.toml`, `uv.lock`, and this Change are affected. Provider
routing, credentials, client configuration, conversation state, installation,
Forge topology, and release identity remain unchanged.
