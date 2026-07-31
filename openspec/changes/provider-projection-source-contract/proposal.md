## Why

The first post-landing GitHub projection failed before any remote write because
`project-github-forge.sh` treated local `refs/heads/main` as the canonical
source. This repository's canonical accepted checkout is `dev`; `main` exists
only as an independently signed provider projection. The Python signing runner
then surfaced the expected child exit as a `CalledProcessError` traceback,
violating the same clean-diagnostic contract being closed.

## What Changes

- Read the canonical GitHub projection source from one explicit Git ref whose
  default is the current `HEAD`, independently of the remote target branch.
- Keep GitHub's target branch fixed at `main` and retain its exact-tip lease,
  complete provider identity rewrite, and immutable provider-native tags.
- Make the signing runner preserve child stderr and exit status without adding
  a Python traceback for an expected command failure.
- Extend the existing offline provider fixture and metadata contract instead of
  adding another projection wrapper or compatibility branch.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=provider projection source and failure diagnostics;
  reuse=extend; change=modify; bind source and target refs separately and keep
  expected runner failure traceback-free;
  facet:lifecycle=publication,validation;
  facet:surface=script,test,docs,openspec;
  facet:authority=accepted-head,provider-main,provider-signature,claim,evidence.

## Out of Scope

- Creating a local `main` branch, moving accepted authority from `dev`, or
  adding a compatibility alias.
- Rewriting `v1.0.45`, either Release, or any existing provider-native tag.
- Changing application payload, installation, AIGW routes, Codex JSONL,
  SQLite, transcript history, or model metadata.
- Treating a local projection fixture as hosted CI or publication proof.

## Impact

Only the GitHub provider projection, its command-scoped signing runner, the
existing provider fixture and release-contract test, canonical Forge operations
documentation, and the existing `ci-diagnostics` evidence chain change.
