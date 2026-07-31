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
- [ ] 3.2 Run the changed-scope plan, parity, exact-HEAD ETHOS executed proof,
  signed commit verification, candidate landing, and accepted-root closeout.

## 4. External acceptance and terminal closeout

- [ ] 4.1 Project independent signed GitLab and GitHub `main` histories with the
  required provider email identities and wait for exact-tip default-branch CI.
- [ ] 4.2 Scan all successful current jobs for actual traceback, ignored
  exception, SocketServer banner, Python warning, abandoned-commit warning, pip
  root warning, and debconf warning.
- [ ] 4.3 Refresh `v1.0.45` publication, release-asset, installed-governance,
  listener, manifest, receipt, serving-digest, route-authority, and bounded
  reliability evidence without republishing or reinstalling an unchanged
  release.
- [ ] 4.4 Archive this change, update the existing Claim and Chronicle to the
  latest facts, create and verify the immutable corrective record, update the
  records index, remove only owned transient residue, and retire this sole own
  lane.
