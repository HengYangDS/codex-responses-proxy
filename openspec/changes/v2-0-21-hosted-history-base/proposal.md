# Release v2.0.21

## Why

Both v2.0.20 Forge pipelines exposed one repository-quality boundary error:
commit-subject verification required the local-only `candidate/dev` ref inside
remote tag checkouts. Remote policy correctly forbids publishing candidate and
Work Lane refs, so the checker—not the branch policy—must be repaired.

## What changes

- derive the comparison base from the first integration ref available in the
  current checkout, preserving local `candidate/dev` priority;
- prove a Forge-shaped checkout detects invalid subjects without a candidate ref;
- advance the immutable failed v2.0.20 publication attempt to v2.0.21.

## Non-goals

- no runtime or provider behavior change;
- no remote candidate/work ref;
- no rewrite or deletion of v2.0.20 tags, runs, or logs.
