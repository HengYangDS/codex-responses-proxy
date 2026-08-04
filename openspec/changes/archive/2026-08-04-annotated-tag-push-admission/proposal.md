## Why

The pre-push guard passes an annotated tag object's SHA to ETHOS as though it
were a commit. Proof records are commit-bound, so valid signed release tags are
rejected with `proof_not_proven` even when the current accepted head is proven.

## What Changes

- Require every pushed tag to be an annotated tag that peels to a commit.
- Require the tagged commit to be contained in the current accepted history.
- Bind protected-write proof admission to the current accepted commit while
  preserving the original tag ref for publication policy evaluation.
- Add a black-box hook contract for branch, annotated-tag, and lightweight-tag
  behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=protected annotated-tag publication admission;
  reuse=extend; change=modify; facet:lifecycle=validation,release;
  facet:surface=git-hook,test; facet:authority=source,test,openspec.

## Impact

Only the repository-owned pre-push guard and its contract are affected. Tag
signatures, tag object identity, Forge release verification, product runtime,
provider protocols, and Codex state remain unchanged.

## Out of Scope

- Rewriting or recreating an existing tag.
- Bypassing hooks or weakening commit proof.
- Moving tag signature verification into the generic Git hook.
