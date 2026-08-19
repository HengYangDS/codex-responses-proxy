## Why

The current Forge projector recreates provider-specific commit histories. That makes
GitLab and GitHub diverge from the local product source, turns email and signer
selection into a source-rewrite operation, and prevents exact SHA parity.

## What Changes

- **BREAKING** Replace provider-history replay with direct publication of the exact
  local signed commit and tag objects.
- **BREAKING** Remove continuity maps, provider-specific commit identities, and
  Forge-to-Forge history reconstruction.
- Publish `main` and `dev` atomically to one selected Forge from the local source;
  publish `proposal/*` independently when explicitly selected.
- Require the selected Forge's verified account email and trust anchor to accept
  the existing local commit signature; never rewrite the object.
- Make the read-only parity audit require exact commit and tag object equality.
- Preserve Forge independence, local closure, and optional remote availability.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: Forge publication projects the exact local signed product
  object rather than creating a provider-native history.
- `ci-diagnostics`: publication and parity require exact commit/tag identity.
- `repository-organization`: remove provider-history mapping and continuity state.

## Impact

The change removes `tools/forge/history.py` and the replay path in
`tools/forge/project.py`, rewrites Forge tests and audit logic, updates release tag
publication, and revises Forge operations and decision records. Existing remote
provider-specific histories are intentionally replaced in one destructive cutover.
