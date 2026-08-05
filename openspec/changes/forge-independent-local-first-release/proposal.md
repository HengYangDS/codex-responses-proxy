## Why

GitLab publication currently waits for and copies a GitHub Release, so an
unavailable or rate-limited GitHub API prevents GitLab from serving as an
independent recovery source. The remote branch namespace also lacks the
repository-family distinction between shared integration refs and local
governance refs.

## What Changes

- **BREAKING** remove every cross-Forge API, asset-download, credential, and
  scheduling dependency from publication.
- Keep the repository-owned native release session as the local, Forge-free
  build and acceptance owner.
- Make each Forge build, sign, verify, and publish only assets produced by its
  own runners on their real platforms.
- Compare equal trees and common-platform payloads only after both independent
  publications exist.
- Permit only `main`, `dev`, and `proposal/*` as remote branch names; keep
  `candidate/*`, `work/*`, and all other governance refs local.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: local-first release ownership, independent Forge
  publication, truthful native platform identity, and remote ref admission.
- `product-interface`: Forge-free local product closure.

## Impact

GitLab CI, publication scripts, release evidence, hooks, governance tests,
release documentation, VERSION, and CHANGELOG change. Runtime request handling,
provider behavior, installed configuration, and Codex state do not change.

## Out of Scope

- Adding a Windows builder to GitLab.
- Changing provider protocol behavior or runtime supervision.
- Making either Forge an installation authority.
