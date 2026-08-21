## Context

See `proposal.md`. Root `pytest.ini` is already the sole pytest owner after the
supervisor repair, but the governance text still stated that every quality
configuration belongs below `.config/checks/`.

## Goals / Non-Goals

**Goals:**

- Align physical placement with native tool discovery.
- Remove configuration indirection and duplicate ownership language.
- Keep direct pytest and IDE use repository-clean.

**Non-Goals:**

- No new quality framework, wrapper, or compatibility surface.
- No movement of tools whose native operation requires explicit config paths.
- No product, release, or runtime behavior change.

## Decisions

1. **Native discovery outranks directory uniformity.** A root-native file is the
   simpler SSOT when the tool and IDEs find it automatically. Uniform nesting
   would require every caller to reproduce path plumbing.
2. **`.config/checks/` remains an explicit-policy home.** Ruff, Ty, coverage,
   architecture, commit, and text policies remain there because callers already
   address them explicitly and no duplicate fallback exists.
3. **Direct-tool residue is ignored at its native location.** `.pytest_cache/`
   is local execution state, not product source or durable evidence.

Rejected alternatives:

- Restore nested pytest configuration: recreates indirection and IDE drift.
- Put pytest configuration in `pyproject.toml`: mixes package metadata with a
  separately owned test policy and conflicts with the repository boundary.
- Add a launcher that always passes `-c`: creates another entity without value.

## Risks / Trade-offs

- [More root files] → Accept the protocol-native surface; root file count is not
  a product metric.
- [Future tool changes its discovery model] → Re-evaluate that tool's sole owner
  rather than preserving placement as compatibility debt.
