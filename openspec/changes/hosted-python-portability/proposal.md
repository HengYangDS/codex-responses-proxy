# Proposal: Hosted Python portability

## Why

GitHub Windows 2025 cannot install the repository-pinned Python 3.12.13 build,
so a source-correct release tip fails before tests start. Patch pins also repeat
one volatile toolchain choice across Forge projections instead of expressing the
product's stable support contract.

## What Changes

- Select the supported Python 3.12, 3.13, and 3.14 release lines in hosted CI.
- Let each official runner or container resolve a currently published stable
  patch in that line.
- Add cross-Forge contract tests that reject Python patch pins in workflow and
  pipeline configuration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: hosted verification must start on every supported operating
  system without depending on a patch build absent from that platform.

## Impact

Only GitHub Actions, GitLab CI, their repository contract tests, and release
notes change. Runtime Python support, product behavior, dependencies, provider
routes, installation, and consumer configuration do not change.
