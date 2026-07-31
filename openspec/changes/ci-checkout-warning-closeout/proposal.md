## Why

The successful GitHub `main` run `30606563610` still logged Git's
`Warning: you are leaving 1 commit behind` while `actions/checkout` replaced a
reused self-hosted workspace. A green conclusion therefore did not satisfy the
repository's clean-diagnostic contract.

## What Changes

- Retain a valid pre-checkout `HEAD` under one repository-private temporary ref
  before every self-hosted GitHub checkout.
- Remove that ref immediately after checkout, including the checkout-failure
  path, without changing runner-global Git configuration.
- Keep the hosted Windows checkout unchanged because its workspace is not the
  reused self-hosted failure surface.
- Extend the provider contract test to reject an unguarded self-hosted checkout,
  a non-final cleanup, a leaked temporary ref, or a global advice workaround.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=reused self-hosted checkout diagnostic integrity;
  reuse=extend; change=modify; retain the displaced revision only for the
  checkout transition and remove the temporary ref on every exit path;
  facet:lifecycle=validation,release;
  facet:surface=ci,test,openspec;
  facet:authority=workflow,test,openspec,claim,evidence.

## Out of Scope

- Rewriting runner-global or user-global Git configuration.
- Suppressing Git warnings generally or hiding unrelated diagnostics.
- Changing the Windows hosted matrix, release identity, tags, Releases, runtime
  payload, AIGW routing, Codex JSONL, SQLite, transcript, or model metadata.
- Treating local workflow tests as proof of a clean hosted run.

## Impact

GitHub verification and release workflows, their repository-owned contract
test, the existing `ci-diagnostics` capability, and its Claim and Chronicle are
affected. No dependency, helper layer, public configuration, or runtime code is
added.
