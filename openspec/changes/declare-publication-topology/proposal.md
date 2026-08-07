## Why

Local verification and the two publication planes must be explicit, independent,
and reproducible. The repository currently has the workflows and remotes but no
repository-owned topology declaration, so publication readiness cannot be
proved without guessing.

## What Changes

- Declare local verification and installation commands in `.ethos/release.toml`.
- Bind GitLab and GitHub to distinct named remotes and CI surfaces.
- Keep `candidate/dev` local-only; permit remote publication only for `main`,
  `dev`, and `proposal/*`.
- Document release asset and trust-anchor inputs without embedding a user path,
  identity, credential, or Forge URL in product source.

## Non-goals

- No remote push, tag, release, or credential mutation.
- No change to AIGW, Workstation, ETHOS, JetBrains products, or Codex history.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: declare the local-first verification/install surface and
  independent GitLab/GitHub publication topology.
