## Why

GitLab `main` CI treats every untagged commit as an unpublished release candidate. After `v1.0.45` was published, the next main projection still carried `VERSION=1.0.45`, so the release checker correctly rejected `--prepare-release` and left pipeline 3959 red.

## What Changes

- Select exact tag validation for tag pipelines.
- On `main`, use ordinary GitLab provider validation when `v$(cat VERSION)` already exists; use release preparation only while that tag is absent.
- Lock the three-way dispatch with the repository release-contract test.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: successful GitLab main validation distinguishes a published release train from a pending release instead of emitting an expected release-state failure.

## Out of Scope

- Rewriting `v1.0.45`, changing `VERSION`, or publishing another release.
- Changing GitHub validation, runtime behavior, AIGW configuration, Codex JSONL, SQLite, transcripts, or model metadata.
- Treating local proof as hosted CI, publication, installation, or runtime evidence.

## Impact

Only the GitLab verification projection, its release-contract test, the `ci-diagnostics` requirement, and bounded evidence carriers change.
