## 1. Diagnose and specify

- [x] 1.1 Inspect current GitHub and GitLab default-branch and `v1.0.45` tag
  logs, separating actual diagnostics from test names containing diagnostic
  words.
- [x] 1.2 Reproduce the self-hosted checkout warning and prove that a temporary
  non-branch ref removes it without changing checkout output or global config.
- [x] 1.3 Bind the change to the existing `ci-diagnostics` capability and
  `ci-log-hygiene-20260730` Claim without creating duplicate semantic owners.

## 2. TDD implementation

- [x] 2.1 Add the workflow contract first and observe the expected failure on
  the missing pre-checkout retention and always-running cleanup.
- [x] 2.2 Add only the temporary-ref lifecycle around each self-hosted checkout
  in verification and release; leave hosted Windows unchanged.
- [x] 2.3 Prove the focused contract passes and rejects global Git advice
  suppression, missing cleanup, wrong ordering, and Windows projection.

## 3. Source proof and landing

- [x] 3.1 Run GitHub/GitLab provider and release contracts, strict OpenSpec,
  Markdown, release metadata, Ruff, format, types, structure, docstrings,
  statement and branch coverage above 95%, and Python 3.12-3.14 matrices.
- [x] 3.2 Run the changed-scope plan, retain the declared generic parity state,
  and complete exact-HEAD ETHOS executed proof plus signed commit verification.
- [x] 3.3 Transfer candidate landing, accepted-root closeout, hosted Forge
  verification, runtime refresh, corrective record creation, and lane retirement
  to the post-archive operational sequence without claiming them here.

## Post-archive operational sequence

These are external lifecycle transitions, not incomplete OpenSpec Change
tasks. Their truth must be established from fresh local, Forge, runtime, and
repository-family evidence:

1. Land the proven source through candidate and accepted roles.
2. Project independent signed GitLab and GitHub `main` histories and wait for
   exact-tip default-branch CI.
3. Scan every successful current job for prohibited diagnostics.
4. Refresh `v1.0.45` publication, asset, installation, runtime, route, and
   bounded-reliability evidence without republishing or reinstalling the
   unchanged release.
5. Reclose the Claim and Chronicle, create and verify the immutable corrective
   record, update the records index, remove only owned transient residue, and
   retire this sole own lane.
