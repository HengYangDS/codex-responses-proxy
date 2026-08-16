## Why

The accepted source contains seventeen post-2.0.39 commits that complete the
quality-policy and architecture-documentation convergence. A forward release
gives that exact source one immutable product identity without rewriting prior
tags or Releases.

## What Changes

- Advance the sole version carrier from 2.0.39 to 2.0.40.
- Record the quality, architecture, and locked-toolchain changes in the
  Changelog.
- Prove and archive the exact release source before independent publication.

## Impact

This patch release changes repository policy, documentation, and development
tooling. It does not change provider routing, proxy protocol behavior, client
configuration, conversation state, or the installed runtime before a verified
release asset is explicitly installed.
