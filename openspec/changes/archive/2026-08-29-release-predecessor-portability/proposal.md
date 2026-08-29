## Why

The release-compatibility job resolves an exact predecessor correctly but reads
that value with POSIX shell syntax on every runner. PowerShell therefore passes
an empty tag to GitHub CLI and silently downloads the latest release instead of
the predecessor.

## What Changes

- Consume the existing GitHub Actions environment value through expression
  interpolation, which is independent of the runner shell.
- Keep predecessor selection in the existing publication module and workflow
  generation in the existing CUE source of truth.
- Add a workflow contract that rejects the platform-specific variable form.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This repairs the implementation of the existing release-governance
contract; it does not change product behavior.

## Impact

The CUE-owned GitHub workflow projection and its contract test change. No new
command, downloader, dependency, configuration surface, or compatibility layer
is introduced.
