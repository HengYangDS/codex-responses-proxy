## Why

GitLab verification repeatedly downloads UV, Python, and the isolated build
backend from the public internet. The project tests pass when those downloads
complete, but slow links make otherwise valid pipelines fail before repository
verification begins.

## What Changes

- Use immutable GitLab verification images for the supported Python boundaries;
  each image already contains the repository-selected UV and Python runtime.
- Keep dependency resolution and package bytes governed by `uv.lock`; the image
  supplies the executor, not a second dependency authority.
- Install locked product dependencies and quality tools without building the
  source project in the bootstrap environment, then let Nox build and test the
  wheel through the existing graph.
- Keep the release image and the independent GitHub workflow unchanged unless
  an equivalent verified simplification is required.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: Hosted verification must distinguish repository failures
  from runner bootstrap failures and avoid redundant public-network bootstrap.

## Impact

The change affects GitLab verification bootstrap, its executable contract tests,
and CI documentation. It does not change proxy traffic, provider behavior,
client configuration, release identity, or Forge independence.
