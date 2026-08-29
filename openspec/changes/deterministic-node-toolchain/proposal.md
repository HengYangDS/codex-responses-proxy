## Why

Fresh Forge jobs resolve OpenSpec through the mise npm backend even though the repository pins only the top-level version. The unowned transitive graph can change independently and has already made identical source pass on one Forge context and fail on another.

## What Changes

- Make `package.json` and `package-lock.json` the sole owner of OpenSpec, Prettier, and their complete npm dependency graph.
- Pin the public npm registry at repository scope so host configuration cannot rewrite lock metadata or trust-key discovery.
- Keep mise responsible only for language runtimes and standalone executables.
- Install and audit the locked npm graph before governance on both Forge projections.
- Resolve Node tools from the repository-local executable directory on POSIX and Windows.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a repository-tool supply-chain correction; product behavior does not change.

## Impact

The repository tool manifests, governance composition, provider-neutral CUE CI graph, generated GitHub/GitLab projections, and focused contracts change. Runtime routing, lifecycle behavior, native assets, and public CLI semantics do not.
