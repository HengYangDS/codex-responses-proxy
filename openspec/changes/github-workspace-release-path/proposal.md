## Why

The Linux release shell runs inside a job container, while artifact upload is
resolved by a host action. Expanding the host expression inside the container
writes outside the shared mount and leaves the uploader with no files.

## What Changes

- Write the Linux asset to `$GITHUB_WORKSPACE` inside the container shell.
- Keep `${{ github.workspace }}` as the upload action input.
- Release the immutable forward fix as `v2.0.30`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: Distinguish the container runtime workspace path from the
  equivalent host action expression.

## Impact

GitHub release workflow, its contract test, release metadata, and no production
runtime code. GitLab remains an independent unchanged release plane, and the
failed `v2.0.29` publication remains immutable.
