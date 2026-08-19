# GitLab Tag Verification

## Why

The GitLab tag pipeline passed a retired Forge positional token to the current
provider-neutral tag verifier. Cyclopts correctly rejected that fourth argument,
so the immutable `v2.0.46` release could not complete on GitLab.

## What Changes

- Call the product tag verifier with exactly repository, tag, and trust anchor.
- Add a repository contract that fixes this public CI grammar.
- Publish the correction as `2.0.47`; `v2.0.46` remains immutable release
  evidence.

## Non-goals

- no tag rewrite;
- no Forge-specific verification parser;
- no change to Git object signing or transport authentication.
