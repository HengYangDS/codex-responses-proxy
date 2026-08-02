## Why

GitHub Windows CI exposes two defects that block the forward release carrying
route-scoped 429 protection: one test constructs a platform path with a literal
slash, and process discovery discards its batch inventory before performing one
PowerShell/CIM query per PID.

## What Changes

- Compare rendered launchd log paths using native path construction.
- Reuse each batch process command line on non-Darwin hosts while preserving
  Darwin native argv identity and per-PID pre-signal revalidation.
- Prove the batch-query boundary and run the full portable release gates.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: subject=portable process discovery; reuse=extend;
  change=modify; preserve exact process identity while eliminating redundant
  non-Darwin host queries; facet:lifecycle=validation,installation,uninstall;
  facet:surface=runtime,test,ci,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Changing provider quotas, route concurrency, HTTP retry semantics, client
  configuration, AIGW, Codex persistence, or JetBrains surfaces.
- Raising hosted CI timeouts instead of removing redundant host queries.
- Weakening per-PID identity proof before a process mutation.

## Impact

The process inventory implementation, its focused tests, one launchd rendering
assertion, release notes, hosted CI, and the pending 2.0.7 release are affected.
Provider routing, quotas, client configuration, AIGW, Codex persistence, and
JetBrains surfaces are unchanged.
