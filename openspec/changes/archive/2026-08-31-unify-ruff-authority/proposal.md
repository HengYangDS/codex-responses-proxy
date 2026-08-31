## Why

Ruff lint, formatting, and public-docstring policy currently use two native
configuration files. The duplicate docstring owner creates avoidable drift and
forces orchestration to repeat policy selection.

## What Changes

- Make `.config/quality/native/ruff.toml` the sole Ruff configuration authority.
- Delete the dedicated docstring configuration.
- Keep public-docstring scope explicit in the existing Nox quality sessions.
- Update the responsibility contract and its regression test.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a quality-policy refactor; product and runtime behavior do not
change.

## Impact

Only Ruff configuration, quality orchestration, its responsibility map, and the
quality contract test change. Provider behavior, request handling, lifecycle,
release identity, and supported platforms are unaffected.
