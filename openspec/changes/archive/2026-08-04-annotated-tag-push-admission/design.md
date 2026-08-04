## Context

Git supplies the local object ID to `pre-push`. For an annotated tag that ID is
the tag object, not its commit. ETHOS proof is intentionally commit-bound.

## Decisions

1. Branch pushes retain their existing admission head.
2. Tag pushes must name an annotated tag object and peel to a commit.
3. The peeled commit must be an ancestor of or equal to the current accepted
   checkout head.
4. ETHOS evaluates the original remote tag ref against the current accepted
   commit. Release tooling remains responsible for signer and exact tag-object
   verification.

## Risks / Trade-offs

- A direct tag push is not itself signature verification. Existing release
  tooling and hosted release gates remain the signature authority.
- A tag for an unrelated commit is rejected before ETHOS admission.
- Lightweight tags are rejected rather than silently normalized.

## Migration Plan

Prove the hook through a black-box test, run exact-head gates, land through the
candidate train, and retry only the unchanged missing tag objects.
