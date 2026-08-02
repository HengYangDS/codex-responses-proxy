## Why

GitLab's Linux quality job for `v2.0.6` measured 94.68 percent branch coverage
because the successful Darwin-native argv path was exercised only by a real
Darwin integration test. The runtime fix is valid, but release admission must be
host-independent and strictly above the 95 percent floor.

## What Changes

- Exercise the successful `kern.procargs2` decoding path through a synthetic
  `sysctl` contract on every supported test host.
- Keep the real child-process integration restricted to Darwin.
- Publish the repair as the forward-only `v2.0.7` train and retain failed
  `v2.0.6` tags and hosted jobs unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=host-independent native-parser verification;
  reuse=extend; change=add; require a synthetic successful native-wire contract
  on every supported test host while retaining real integration on its native
  operating system; facet:lifecycle=validation,release;
  facet:surface=test,quality,ci,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Changing process discovery, lifecycle, provider routing, or installed runtime
  behavior.
- Lowering or excluding the branch-coverage floor.
- Rewriting failed tags, hosted jobs, Releases, or Codex persistence.

## Impact

Only the process-identity test, `VERSION`, `CHANGELOG.md`, and this change record
are affected. Production runtime code, provider routes, credentials, Codex
history, AIGW, and JetBrains surfaces remain unchanged.
