# Forward-fix the failed release

## Why

`v2.0.15` remains immutable failure evidence. The provider-isolation repair
must ship under a new SemVer patch rather than rewriting or reusing that tag.

## What Changes

- Advance `VERSION` to `2.0.16`.
- Record the release fix in the Changelog.
- Keep the installation example aligned with the current asset name.

## Non-goals

- No runtime, provider, signing, or release-policy behavior change.
