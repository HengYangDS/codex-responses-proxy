## 1. Release identity

- [x] 1.1 Set `VERSION` to `3.1.7` and verify release metadata with
      `python -m tools.release.metadata --prepare-release`.
- [x] 1.2 Move the accepted post-3.1.6 entries from `CHANGELOG.md` Unreleased
      into a dated `3.1.7` section and verify the Changelog/version contract.

## 2. Source acceptance

- [x] 2.1 Run `openspec validate release-3-1-7 --strict --json` and the complete
      repository proof on the exact release source tree.
- [x] 2.2 Confirm this release Change adds no product-spec delta and archive it
      through the official OpenSpec lifecycle.

## Post-archive lifecycle

Integrate the archived source into candidate and accepted truth, create and sign
the exact `v3.1.7` tag, build the native asset set, publish identical objects to
GitLab and GitHub, and upgrade the formal runtime only after candidate
installation, rollback, recovery, service-health, and real Responses checks pass.
