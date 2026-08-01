## Context

`origin/main` has no Git ancestor in the current accepted ref, but its tip has
one identity-neutral match in the accepted history. The only accepted
descendants after that match are local and unpublished. GitHub `main` already
projects an earlier point in the same semantic lineage.

## Decisions

1. GitLab remains the canonical commit-identity domain. GitHub remains an
   append-only projection with its own verified email and signing key.
2. Convergence is a rebase of unpublished accepted descendants onto the exact
   current GitLab tip. It is not a merge of unrelated duplicate histories.
3. Every replayed successor commit is re-signed with the selected GitLab
   identity. Existing remote commits, tags, Releases, and evidence are not
   mutated.
4. Ordinary publication resumes only after the successor history passes the
   complete local gate and ETHOS proof. GitLab then fast-forwards; GitHub maps
   its existing tip uniquely and appends only missing projections.
5. The CI specification is decomposed by invariant: identity, append-only
   continuity, unique matching, failure diagnostics, convergence, and key
   rotation each have one semantic owner.

## Verification

- Prove the remote GitLab tip has exactly one identity-neutral accepted match.
- Prove the unpublished successor tree equals the pre-convergence candidate.
- Require diagnostic-free strict OpenSpec validation.
- Run the complete Python 3.12-3.14 quality and test matrix with statement and
  branch coverage above 95 percent.
- Verify every successor commit email and SSH signature before ETHOS executed
  proof and landing.

## Rollback

Before publication, restore the work-lane ref to its recorded predecessor. No
remote or runtime rollback is needed because this change mutates neither.
