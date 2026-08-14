## Why

The accepted GitLab repair now binds post-sync execution to the Python selected
by uv and caches managed compatibility runtimes by target platform. Version
2.0.33 predates that accepted source, so publishing it under the old identity
would violate the repository's release contract.

## What Changes

- Advance the single release identity from 2.0.33 to 2.0.34.
- Record the accepted GitLab execution and cache repair in the Changelog.
- Remove the release version duplicated in README installation examples.
- Require an accepted unreleased repair to advance through one newer SemVer
  patch without rewriting an existing tag, run, Release, or asset.

## Boundary

This Change modifies release identity, its specification, and version-neutral
installation examples only. It does not change proxy runtime behavior,
provider routing, client configuration, release payload construction, or
either Forge's independent authority.
