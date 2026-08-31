## 1. Release identity

- [x] 1.1 Set `VERSION` to `3.1.8` and verify release metadata with
      `python -m tools.release.metadata --prepare-release`.
- [x] 1.2 Move the accepted replay correction from `CHANGELOG.md` Unreleased
      into a dated `3.1.8` section and verify the Changelog/version contract.

## Post-archive lifecycle

After the release identity is complete, run strict OpenSpec validation and
exact-HEAD repository proof, archive this spec-free Change, integrate the
archived source into candidate and accepted truth, create and sign `v3.1.8`,
build and publish byte-identical native assets to both Forges, upgrade the
formal runtime transactionally, and confirm the unchanged ETHOS task can
continue before retiring this Work Lane.
