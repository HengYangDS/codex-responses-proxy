# Tasks

- [x] 1.1 Replace GitHub workflow Shell contracts with pytest.
- [x] 1.2 Route GitLab and GitHub verification through the pytest owner.
- [x] 2.1 Replace Forge context, projection, and signature Shell owners.
- [x] 2.2 Replace tag and publication Shell owners.
- [x] 2.3 Replace the remaining Shell contract tests and delete wrappers.
- [ ] 3.1 Align documentation and command help with the portable owners.
- [ ] 3.2 Run quick, quality, Python 3.12/3.13/3.14, release, and strict OpenSpec gates.
- [ ] 3.3 Prove Shell ELOC and cross-platform risk decreased, then archive and land.

## Requirement To Task To Proof

| Requirement | Tasks | Proof |
| --- | --- | --- |
| `product-interface:Repository automation has one portable semantic owner` | `2.1` | `tests/forge/test_workflow_contracts.py; tests/forge/test_tagging.py` |
| `product-interface:Repository automation has one portable semantic owner` | `2.2` | `tests/release/test_publish_gitlab.py; tests/release/test_metadata.py` |
| `product-interface:Repository automation has one portable semantic owner` | `2.3` | `tests/governance/test_repository.py` |
| `product-interface:Repository automation has one portable semantic owner` | `3.2` | `nox -s quality tests-3.12 tests-3.13 tests-3.14 release` |
