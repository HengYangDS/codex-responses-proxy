# Design

## Decision

Run the declared uv resolver against the existing direct constraints and commit
only its stable lock delta. `pyproject.toml` continues to own direct
requirements; `uv.lock` owns their transitive closure. Repeating the resolution
must produce no further diff.

## Verification

Run the locked Nox quick, quality, Python 3.12-3.14, and release sessions, then
execute exact-HEAD proof and archive through the governed lifecycle.
