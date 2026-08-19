## Why

Native Windows verification mixed a POSIX mock home with Windows path normalization. The default installation was therefore misclassified as an alternate root even though production path selection was correct.

## What Changes

- derive default and alternate service-root fixtures from the host-native default directory;
- preserve deterministic isolation assertions for alternate roots;
- keep lifecycle implementation, service identity, runtime state, and live installation unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a test-only portability correction.

## Impact

Only the lifecycle context test and this completed change record are affected. No public API, dependency, provider, installation, or runtime behavior changes.
