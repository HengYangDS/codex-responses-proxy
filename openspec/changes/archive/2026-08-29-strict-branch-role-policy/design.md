## Context

Current ETHOS closeout parses the accepted commit's branch-role table strictly.
The legacy transition row is no longer authoritative, while `release_mirror`
and `canonical_sibling_worktrees` are required fields. Keeping both models in
one carrier makes ordinary status appear healthy but fails only at closeout.

## Goals / Non-Goals

**Goals:**

- Keep one complete, explicit branch-role policy.
- Preserve exact-object fast-forward promotion from candidate to `dev` and
  `main`.
- Delete the obsolete transition model.

**Non-Goals:**

- Add fallback parsing, migration adapters, or another policy carrier.
- Change product runtime or release behavior.

## Decision

Use the current seven-field branch-role table already adopted by ETHOS and
AIGW. `release_mirror = "accepted_ff"` makes the release root a deterministic
projection of the accepted commit; `canonical_sibling_worktrees = true`
declares the repository's existing physical layout. No transition array or
compatibility branch remains.

## Risks / Trade-offs

- Future schema changes can invalidate the carrier -> the repository gate must
  parse the current strict policy before expensive release work.
