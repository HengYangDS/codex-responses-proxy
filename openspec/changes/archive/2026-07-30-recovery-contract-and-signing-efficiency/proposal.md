## Why

The released recovery implementation correctly separates loaded runtime identity
from the committed candidate manifest, but canonical prose still states the old
single-projection contract. Provider history projection also invokes the
workstation signing bridge once per commit unless the caller manually prepares
a shared agent, turning a 153-commit projection into repeated Keychain startup.

## What Changes

- Make README, governance, and the complete runtime-upgrade spec describe the
  same two-projection recovery invariant as the implementation.
- Add one repository-owned projection runner that preloads the exact provider
  key once when an agent is unavailable, then delegates the existing isolated
  projection under that bounded agent.
- Keep the low-level projection scripts transport-agnostic and fail closed when
  signing inputs or provider identity are wrong.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: subject=recovery identity documentation; reuse=extend;
  change=modify; facet:lifecycle=recovery,documentation;
  facet:surface=runtime,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.
- `ci-diagnostics`: subject=provider history signing execution; reuse=extend;
  change=modify; facet:lifecycle=release,publication;
  facet:surface=scripts,test,docs;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Changing commit, tag, author, committer, trust-anchor, or remote invariants.
- Persisting an SSH agent beyond one projection command.
- Rewriting historical tag or Release objects.

## Impact

Recovery documentation, the runtime-upgrade spec, provider projection entrypoint,
offline projection tests, release metadata, and operator documentation change.
