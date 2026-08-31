## 1. Release identity

- [x] 1.1 Set `VERSION` to `3.1.10` and verify release metadata with the
      repository release-metadata command.
- [x] 1.2 Move the accepted checkout-preservation correction from Unreleased
      into a dated `3.1.10` section and verify the Changelog/version contract.

## 2. Source acceptance

- [x] 2.1 Pass strict OpenSpec validation and the complete repository source
      gate for the frozen release delta.
- [x] 2.2 Confirm this Change adds no product-spec delta and is ready for the
      official archive transition.

## Post-archive lifecycle

Integrate the archived source into candidate and accepted truth, create and sign
`v3.1.10`, publish byte-identical native assets to both Forges, transactionally
upgrade the formal runtime, prove rollback and forward recovery, then retire the
release Work Lane.
