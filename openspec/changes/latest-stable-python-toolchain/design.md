## Context

This is a bounded quality-tool refresh; see `proposal.md` for motivation.

## Goals / Non-Goals

**Goals**

- Use the current stable declared toolchain.
- Preserve one declaration owner and one resolution owner.
- Prove the existing quality, Python-matrix, and native-release contracts.

**Non-Goals**

- No product, protocol, provider, runtime, version, or publication change.
- No additional package manager, wrapper, compatibility layer, or host path.

## Decisions

| Concern | Decision | Rejected alternative |
| --- | --- | --- |
| Direct pin | Update `pyproject.toml` in place | Add a second version file |
| Resolution | Regenerate `uv.lock` | Preserve stale transitive pins |
| Verification | Reuse repository Nox sessions | Add one-off scripts |

## Risks / Trade-offs

- New diagnostics from `ty` could fail the existing source contract -> run the
  complete static and behavioral gates without suppressions.
- A transitive resolver change could widen the diff -> admit only the lock
  changes required by the direct pin.
