## Context

Tool version output has two distinct fields: a semantic identity owned by the
pin and optional human-readable build metadata. Treating the whole line as the
identity made presentation drift a release blocker.

## Goals / Non-Goals

**Goals:** Admit the exact pinned tool/version with either no suffix or one
space-delimited informational suffix, and prove rejection of near matches.

**Non-Goals:** Parse arbitrary version grammars, accept newer versions, or move
quality policy into provider YAML.

## Decisions

1. `resolve_versioned_tool` remains the single owner for PATH and explicit-path
   selection.
2. A candidate matches when output equals the expected identity or starts with
   that identity followed by one space and non-empty metadata. This matches the
   provider preflight while rejecting `0.0.640`, tabs, and unrelated output.
3. Behavioral fixtures cover plain output, build metadata, wrong versions, and
   misleading prefixes. Provider files remain thin projections.

## Risks / Trade-offs

- Informational metadata is not interpreted -> it is not part of the pinned
  semantic identity and cannot change the selected version.
- Shell matching can become opaque -> keep the predicate in one named helper
  and test its observable selection behavior.
