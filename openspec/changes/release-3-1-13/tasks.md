## 1. Release identity

- [x] 1.1 Define the forward-only SemVer release invariant, advance `VERSION`
  to `3.1.13`, add the accepted local-shell replay correction to
  `CHANGELOG.md`, and verify release metadata validation passes.

## 2. Product evidence

- [x] 2.1 Run `uv run --locked --no-sync nox -s full` once and verify every
  required quality and supported-Python gate passes without warnings.
- [x] 2.2 Run `uv run --locked --no-sync nox -s release` once and verify the
  release, native lifecycle, compatibility, and packaging gates pass.
- [x] 2.3 Run strict OpenSpec validation and verify the completed Change is
  archive-ready.

## Post-archive lifecycle

After source acceptance, archive this Change and integrate the archived source
into candidate and accepted truth. Then create the signed `v3.1.13` tag, publish
the same complete native inventory to GitLab and GitHub, verify both projections,
upgrade the canonical installation transactionally, and prove health, rollback
authority, and residue-free Work Lane retirement. These external effects require
fresh evidence and are not OpenSpec completion checkboxes.
