## Why

The current Forge pipelines repeat the same source proof for one commit and can
accept a Linux-only GitLab release as parity with a complete GitHub release.
That wastes runner time and permits a false dual-Forge release claim.

## What Changes

- Give review, accepted-branch, and tag pipelines one non-overlapping proof
  responsibility each.
- Require both Forge releases to expose the exact complete platform inventory,
  bytes, checksum inventory, signature, and trust identity.
- Assemble and sign one immutable release bundle once; publish it unchanged to
  each optional Forge instead of rebuilding or re-signing per Forge.
- Keep local build, install, exercise, and uninstall independent from Forge
  availability.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-governance`: Define non-duplicative proof contexts and exact complete
  release-bundle parity across optional Forge projections.

## Impact

- GitLab and GitHub workflow triggers and job responsibilities.
- Release bundle assembly, signing, publication, and parity evaluation.
- Release governance documentation and DR-0004.
- Hosted CI duration and release evidence.
