# Portable automation ownership

## Ownership

| Concern | Semantic owner | Projection |
| --- | --- | --- |
| Forge inspection and projection | `tools.forge` Python package | CI command |
| Release tagging and publication | `tools.release` Python package | CI command |
| Workflow and release contracts | pytest | CI test invocation |
| Environment orchestration | nox | local and hosted sessions |

CI configuration selects platforms and credentials. It does not own policy or
business decisions. A platform-specific command is admissible only when the
platform itself requires it and the adapter contains no repository policy.

## Migration

Each slice first establishes equivalent Python tests, then changes every caller,
then deletes the Shell owner in the same commit. No forwarding wrapper or
compatibility alias remains.

## Verification

Focused tests precede the complete quick, quality, Python 3.12/3.13/3.14, and
release sessions. The repository inventory must show fewer source files and
effective lines while preserving all supported native platforms.
