## Why

Protocol-v2 upgrades reject every real cross-version successor because the old
listener compares the requested new identity with its own frozen identity
instead of the committed payload on disk. The failure leaves a correct new
payload behind a recovery hold while the old process continues serving.

## What Changes

- Make the old listener validate the exact committed successor manifest and
  serving-file set before preparing a handoff child.
- Preserve the current fail-closed identity checks for malformed, partial, or
  mismatched payloads.
- Add an end-to-end cross-version upgrade regression and a supported recovery
  path for the already committed `1.0.36` transaction.

## Capabilities

### New Capabilities

- `runtime-upgrade`: subject=protocol-v2 released-payload upgrade; reuse=new;
  change=add; facet:lifecycle=installation,recovery;
  facet:surface=runtime,listener,control,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

### Modified Capabilities

None.

## Out of Scope

- Codex transcript, session, model metadata, or AIGW configuration changes.
- Weakening signed-source, provider identity, coverage, or Forge publication
  requirements.
- Treating a committed payload, old serving listener, or recovery journal as a
  completed installation.

## Impact

The listener handoff identity owner, source-side deployment recovery,
transaction lifecycle, installation tests, release metadata, and runtime
operator documentation change. Forge publication and Codex/AIGW ownership do
not change.
