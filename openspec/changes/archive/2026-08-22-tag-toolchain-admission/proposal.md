## Why

GitHub release-tag governance executes the repository CI projection contract,
but its job does not install the declared projection toolchain. A valid release
therefore fails because `mise` is absent rather than because the product or tag
is invalid.

## What Changes

- Give tag governance the same repository-owned `mise` action used by source
  governance before running projection-aware tests.
- Add a workflow-contract regression that proves the dependency is declared.
- Regenerate both Forge projections from the single CUE model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The existing release-governance requirement already requires a Forge tag
pipeline to verify the product tag; this change repairs its implementation.

## Impact

The provider-neutral CUE CI graph, its generated GitHub and GitLab projections,
and the focused workflow contract test are affected. Product runtime behavior,
release contents, and provider adapters are unchanged.
