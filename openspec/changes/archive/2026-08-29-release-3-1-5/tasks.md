## 1. Release identity

- [x] 1.1 Set `VERSION` to `3.1.5` and verify strict SemVer metadata.
- [x] 1.2 Add the `3.1.5` Changelog entry for the accepted repository cleanup
      and release-predecessor portability correction.

## 2. Source acceptance

- [x] 2.1 Pass the complete repository proof on the exact release source tree.
- [x] 2.2 Confirm this release Change adds no product-spec delta and archive it
      through the official OpenSpec lifecycle.

## Post-archive lifecycle

Integrate the archived source into candidate and accepted truth, create and sign
the exact `v3.1.5` tag, build the native asset set, publish identical objects to
GitLab and GitHub, upgrade the formal runtime transactionally, and verify
status, doctor, recovery readiness, listener health, and real Responses traffic.
