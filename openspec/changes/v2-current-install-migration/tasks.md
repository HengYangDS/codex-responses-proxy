## 1. Contract and RED

- [x] 1.1 Prove that the sole runtime default is 8792 while explicit CLI and
  environment overrides remain effective.
- [x] 1.2 Prove that an exact v2.0.0 schema-2 projection upgrades, retires
  `replay/event.py`, and restores it on rollback.

## 2. Implementation

- [x] 2.1 Add exact v2.0.0 inventory and entrypoint admission without relaxing
  unknown-manifest rejection.
- [x] 2.2 Derive retired rollback files from the verified prior inventory.
- [x] 2.3 Move the single default to 8792 and reject copied production literals.

## 3. Proof and release

- [ ] 3.1 Run focused tests, strict OpenSpec, release metadata, full quality,
  Python 3.12-3.14 compile, and HEAD-bound proof.
- [ ] 3.2 Publish a new signed dual-Forge patch release with equal trees/assets.
- [ ] 3.3 Install on 8792 and verify manifest, receipt, serving digest, retry,
  compaction, and unchanged original-task acceptance.
