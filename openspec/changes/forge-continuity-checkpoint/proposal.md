# Forge Continuity Checkpoint

## Why

A trusted provider tip can remain an append-only descendant of the last mapped
canonical ancestor while no longer reproducing one canonical commit's full
fingerprint. Automatic matching then has no safe base even though the provider
history, accepted ancestor, and current provider tip are all known exactly.

## What Changes

- Add an explicit three-coordinate continuity input: canonical base, projected
  anchor, and observed provider tip.
- Verify those coordinates before creating any successor commit.
- Keep both provider refs forward-only and preserve independent identities.
- Compare provider histories by their current equal ordered tree suffix rather
  than requiring unrelated historical prefixes to have equal length.

## Non-goals

- Rewriting a published ref, tag, Release, or historical evidence.
- Guessing a base from equal tip trees alone.
- Coupling GitLab publication to GitHub or the reverse.
