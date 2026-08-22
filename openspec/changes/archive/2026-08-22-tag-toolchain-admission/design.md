## Context

See `proposal.md`. The tag-governance test imports the CI projector, whose
renderer invokes CUE through the locked `mise` environment. Review CI already
declares that toolchain; the tag job does not.

## Goals / Non-Goals

**Goals:**

- Make tag governance self-contained on a clean hosted runner.
- Keep GitHub and GitLab workflows generated from the single CUE owner.
- Preserve the existing tag, asset, and publication contracts.

**Non-Goals:**

- Change release metadata semantics or asset composition.
- Add another bootstrap script or provider-specific implementation.

## Decisions

- Add the existing pinned `githubMiseAction` to `tag-metadata`. This reuses the
  repository toolchain SSOT rather than duplicating CUE installation logic.
- Keep the regression in the workflow contract suite because the defect is an
  undeclared job dependency, not a product-runtime behavior.
- Regenerate both YAML projections from CUE even when only one projection's
  bytes change, preserving the one-model discipline.

## Risks / Trade-offs

- **Tag verification gains one setup step** → the action is immutable-pinned
  and uses the already locked tool definitions.
- **A future projector dependency could be omitted again** → the regression
  asserts the tag job declares the projector's toolchain explicitly.
