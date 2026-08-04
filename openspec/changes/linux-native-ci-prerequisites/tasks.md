## 1. Reproduce and repair

- [x] 1.1 Capture pipeline `4489` traces proving Linux `objdump` is absent in
  all Python matrix jobs and the quality job.
- [x] 1.2 Declare Debian `binutils` in both GitLab native-build projections.
- [x] 1.3 Update the focused CI contract so either dependency omission fails.

## 2. Verify and deliver

- [x] 2.1 Pass focused release-metadata and quality-contract tests.
- [ ] 2.2 Pass the full exact-head local quality and Python matrix proof.
- [ ] 2.3 Land forward-only and obtain a successful exact-head GitLab main
  pipeline before resuming release publication.
