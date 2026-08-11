# GitHub container workspace path

## Problem

The Linux release shell runs inside a job container, while artifact upload is
resolved by a host action. Expanding the host expression inside the container
writes outside the shared mount and leaves the uploader with no files.

## Change

- Write the Linux asset to `$GITHUB_WORKSPACE` inside the container shell.
- Keep `${{ github.workspace }}` as the upload action input.
- Release the immutable forward fix as `v2.0.30`.

## Out of scope

- Runtime behavior.
- GitLab release paths.
- Rewriting the failed `v2.0.29` publication.
