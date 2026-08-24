## 1. Publication evidence

- [x] 1.1 Add a regression that passes real GitHub- and GitLab-adapter evidence,
      including validated job maps, through `publication.verify`.
- [x] 1.2 Normalize hosted evidence at the composition boundary without
      weakening the evaluator's closed schema.
- [x] 1.3 Re-run live `v3.0.3` verification and retain a verified receipt.
- [x] 1.4 Model GitLab publication credential kind explicitly and prove exact
      environment-variable and header selection for CI and maintainer paths.

## 2. macOS host projection

- [x] 2.1 Extend native lifecycle acceptance to compare exact product-owned
      registrations, overrides, and plists before and after every lifecycle.
- [x] 2.2 Run native lifecycle success and failure paths and prove zero net test
      residue while the formal service remains healthy.
- [x] 2.3 Record a bounded exact-label migration procedure for historical
      override records without adding compatibility cleanup to product teardown.

## 3. Acceptance

- [x] 3.1 Run focused publication and supervision tests.
- [x] 3.2 Run strict OpenSpec, quality, and Python 3.12/3.13/3.14 gates.
- [ ] 3.3 Archive the Change, land the accepted source, publish the patch release,
      upgrade the formal runtime transactionally, and verify status, doctor,
      recover, `/healthz`, provider switching, and continuous requests.

## Requirement To Task To Proof

| Requirement                                                                    | Task  | Proof                                                                          |
| ------------------------------------------------------------------------------ | ----- | ------------------------------------------------------------------------------ |
| `release-governance:Hosted evidence has one composition boundary`              | `1.1` | `tests/release/publication/test_cli.py; live dual-Forge verification receipt`  |
| `release-governance:GitLab publication preserves credential semantics`         | `1.4` | `tests/release/test_publish.py; tests/release/test_publish_gitlab.py`          |
| `runtime-upgrade:macOS lifecycle leaves no new persistent service projections` | `2.1` | `tests/release/test_native_lifecycle.py; native exact-label lifecycle receipt` |
