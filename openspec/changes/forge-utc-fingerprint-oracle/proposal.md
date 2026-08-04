## Why

Git 2.55 renders an exact UTC strict-ISO commit date with `Z`, while older
hosted Git versions render the same instant with `+00:00`. The independent
fingerprint test oracle treated those equivalent forms as different bytes and
therefore failed the Linux Python matrix after the product implementation had
already produced the canonical value.

## What Changes

- Normalize the independent Git-command oracle's exact UTC date lines to `Z`.
- Keep the production fingerprint grammar, commit semantics, and projection
  admission unchanged.
- Prove the oracle on the focused history suite and the full supported Python
  matrix.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: require the Forge fingerprint oracle to treat Git's two
  strict-ISO UTC renderings as the same instant without weakening any other
  identity-neutral fingerprint byte.

## Out of Scope

- Changing commit dates, commit objects, production fingerprint semantics, or
  provider history.
- Rewriting or force-updating either Forge.
- Changing runtime, installation, provider routing, or Codex conversation state.

## Impact

Only `tests/forge/test_history.py`, this OpenSpec change, and the resulting
`ci-diagnostics` requirement. Hosted CI remains a separate external proof.
