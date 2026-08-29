## 1. Release identity

- [x] 1.1 Set `VERSION` to `3.1.6` and verify strict SemVer metadata.
- [x] 1.2 Add the `3.1.6` Changelog entry for the accepted stable-toolchain
      refresh and strict branch-role policy.

## 2. Source acceptance

- [x] 2.1 Pass the complete repository proof on the exact release source tree.
- [x] 2.2 Confirm this release Change adds no product-spec delta.
- [x] 2.3 Confirm the completed Change is ready for the official OpenSpec
      archive operation.

## Post-archive lifecycle

Integrate the archived source into candidate and accepted truth, create and sign
the exact `v3.1.6` tag, build the native asset set, publish identical objects to
GitLab and GitHub, upgrade the formal runtime transactionally, and verify
status, doctor, recovery readiness, listener health, and real Responses traffic.
