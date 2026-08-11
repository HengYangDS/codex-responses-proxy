## Context

See `proposal.md`. GitHub runs the Linux build step inside a pinned container, while JavaScript actions execute through the host runner. `runner.temp` is not path-identical across that boundary; `github.workspace` is the existing shared mount.

## Goals / Non-Goals

**Goals:**

- Preserve the pinned Linux build container.
- Give the build and uploader one exact shared output directory.
- Keep GitLab and GitHub independent.

**Non-Goals:**

- Change production runtime behavior.
- Add path translation, wrappers, or another artifact owner.
- Modify the GitLab release workflow.

## Decisions

Use `${{ github.workspace }}/.release-assets/linux-x86_64` for both the release session output and `upload-artifact` input. The workspace is already mounted across the container and host action boundary. Using `runner.temp` was rejected because it has distinct container and host identities; copying after the build was rejected because it creates a second path and failure surface.

## Risks / Trade-offs

- Workspace residue could affect later steps → use a release-owned hidden directory in the ephemeral checkout and upload only its platform leaf.
- A future workflow edit could split the paths again → keep one focused contract test asserting exact equality and rejecting `runner.temp` in the Linux job.

## Migration Plan

Publish v2.0.29 as a forward fix. Do not rewrite or delete the failed v2.0.28 tag or runs.
