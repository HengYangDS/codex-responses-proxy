## Why

The canonical runtime has crossed the one-release carrier migration bridge and now owns a validated `runtime-config.json`. Retaining environment-derived carrier creation would preserve a compatibility path with no remaining product consumer and weaken the single runtime authority.

## What Changes

- Remove the release-scoped private-role fallback that created
  `runtime-config.json` for the completed `2.0.52 → 2.0.55` migration.
- Require listener, handoff-child, and watchdog startup to activate the existing executable-owned carrier through one identical path.
- Delete bridge-only unit and published-predecessor fixtures after preserving the general forward-upgrade contract.
- Replace historical-form blacklists with the positive invariant that every private role reads one valid carrier before product startup.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: Make the executable-owned runtime carrier mandatory for every private role after the bounded migration release.

## Impact

Private startup composition, runtime-carrier tests, native compatibility coverage, release identity, and the runtime-upgrade specification change. Public CLI grammar, provider routing, credentials, AIGW, Codex state, and the installed `2.0.55` runtime remain unchanged until the signed successor is accepted.
