## Context

The current model has two owners for Node repository tools: top-level versions in `mise.toml`, while the npm backend resolves their transitive packages dynamically. A fresh resolution selected `fastq@1.20.2`, whose trust evidence differed from the earlier release, so identical source failed depending on when and where resolution occurred. Host npm configuration can also redirect registry and signing-key metadata.

## Goals / Non-Goals

**Goals:**

- Reproduce the complete Node repository-tool graph from one immutable lock.
- Keep signature and provenance validation enabled.
- Make local, GitHub, and GitLab governance use the same install path.
- Keep Node tool invocation portable across POSIX and Windows.
- Advance the locked runtime and Python graphs to current stable releases while preserving one authority per ecosystem.

**Non-Goals:**

- Add retries, timeouts, trust exclusions, a wrapper script, or another package manager.
- Change product runtime behavior or release artifacts.
- Redesign the broader quality system in this release atom.

## Decisions

1. `package.json` and `package-lock.json` exclusively own OpenSpec and Prettier. Their mise npm entries are deleted, removing dynamic transitive resolution.
2. `.npmrc` binds the repository to `https://registry.npmjs.org/`. This is a positive authority declaration: a global mirror must not alter dependency bytes or registry-signature keys.
3. CI runs `npm ci --ignore-scripts` and `npm audit signatures` before governance. Install scripts are unnecessary for these tools and remain disabled.
4. Governance invokes declared Node tools through `npm exec --offline`. npm owns platform-specific executable resolution, while offline mode prevents an undeclared network install or ambient fallback.
5. `.config/ci/pipeline.cue` remains the sole CI topology owner and regenerates both Forge YAML projections.
6. `mise.toml` and `pyproject.toml` own direct stable pins; `mise.lock`, `uv.lock`, and the CUE-generated Forge projections bind their complete resolved graphs and immutable container identities.

## Risks / Trade-offs

- The public npm registry becomes an explicit repository-tool dependency -> the lock preserves package identities and integrity; offline work can reuse a populated cache, but fresh installation correctly requires the declared authority.
- Another Node tool could be added inconsistently -> focused contracts require all mise tools to be non-npm and verify the exact locked development dependency set.
