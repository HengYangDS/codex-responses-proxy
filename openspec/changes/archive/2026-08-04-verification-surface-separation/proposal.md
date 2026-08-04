## Why

The Python compatibility and quality sessions each build a PyInstaller onefile
binary and use it for the complete test inventory. The release session repeats
the same native build. This couples Python compatibility proof to native
extraction latency, repeats the most expensive distribution work four times,
and has produced non-deterministic listener-start failures despite repeated
single-session success.

## What Changes

- Run Python compatibility and quality against the console executable installed
  from each session's built wheel.
- Give the native executable a distinct environment identity.
- Make the release session the sole native build owner and require it to run
  both CLI and real handoff black-box tests before packaging.
- Preserve the complete behavior inventory, supported Python matrix, coverage,
  and native no-Python acceptance.
- Repair task carriers that incorrectly modeled candidate landing as a
  pre-archive checkbox. Landing remains unproved and moves to the active claim
  as an explicit post-archive transition.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: subject=verification distribution surfaces; reuse=extend;
  change=modify; facet:lifecycle=validation,release;
  facet:surface=nox,test; facet:authority=source,test,openspec.

## Impact

Repository-owned verification composition, its tests, and the malformed task
boundary change. Product runtime, provider protocols, release contents, and
user configuration do not.

## Out of Scope

- Weakening coverage or removing behavior tests.
- Changing the supported Python matrix.
- Changing the native executable format or release assets.
