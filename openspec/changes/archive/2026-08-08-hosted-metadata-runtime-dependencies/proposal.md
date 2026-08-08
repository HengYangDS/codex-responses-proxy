# Hosted metadata runtime dependencies

## Why

The GitLab release-metadata job executes repository product tooling. Installing
only the quality dependency group omits the product runtime and makes the job
fail before metadata validation.

## What changes

- Install the complete locked environment in the GitLab metadata job.
- Keep quality-only jobs on the smaller quality environment while fetching the
  release tags their chronology tests require.
- Execute package-aware repository tools through module entrypoints.
- Enforce the distinction with a repository contract test.

## Non-goals

- No release, runtime, provider, or GitHub workflow behavior changes.
