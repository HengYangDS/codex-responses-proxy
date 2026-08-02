## Why

GitLab pipeline 4064 measured 94.91 percent branch coverage because two
Darwin-specific outcomes were exercised only incidentally on a Darwin host.
Release proof must be deterministic on Linux rather than depend on the host
that happens to run the suite.

## What Changes

- Exercise the default Darwin state directory while running on every host.
- Exercise rejection of an incomplete Darwin process-argument payload through
  the existing synthetic `sysctl` boundary.
- Keep production code, the strict coverage floor, and failed release history
  unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=host-independent native-parser verification;
  reuse=extend; change=modify; require deterministic valid, incomplete-payload,
  and platform-default contracts without invoking a foreign operating-system
  call; facet:lifecycle=validation,release;
  facet:surface=test,quality,ci,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Changing production runtime, process discovery, provider routing, or client
  configuration.
- Lowering or excluding the statement or branch-coverage floors.
- Rewriting failed tags, hosted jobs, Releases, or Codex persistence.

## Impact

Only two tests, the pending `2.0.7` Changelog entry, and this change record are
affected. Runtime behavior, provider routing, credentials, Codex persistence,
AIGW, and JetBrains surfaces remain unchanged.
