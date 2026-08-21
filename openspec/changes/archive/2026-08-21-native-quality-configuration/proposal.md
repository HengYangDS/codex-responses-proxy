## Why

Quality configuration had been organized by directory convention rather than
each tool's native discovery model. That forced explicit pytest path plumbing
and left the policy text inconsistent with the repository's actual SSOT.

## What Changes

- Define tool-native configuration as the positive ownership rule.
- Prefer root placement when a tool and IDEs discover the file there natively.
- Keep `.config/checks/<concern>/` for policies that require explicit addressing.
- Ignore pytest's root cache so direct CLI and IDE use leaves no visible residue.
- Add contract coverage for the ownership rule and cache boundary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a configuration, documentation, and quality-contract correction;
it does not change proxy behavior.

## Impact

The repository quality policy, ignore boundary, and quality contract tests are
affected. Product code, runtime state, provider behavior, and release identity
are unchanged.
