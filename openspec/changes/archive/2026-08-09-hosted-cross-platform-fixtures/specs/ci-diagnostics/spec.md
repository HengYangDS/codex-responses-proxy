# CI Diagnostics Delta

## ADDED Requirements

### Requirement: Hosted fixtures are platform-default independent

Repository tests SHALL reach the intended Forge and signing behavior without
depending on a runner's Git default branch or text newline translation.

#### Scenario: Clone already has `main`

- **WHEN** a hosted Git configuration makes `main` the clone's current branch
- **THEN** the divergent-history fixture resets that branch to `origin/main`
- **AND** continues to test projection rejection rather than fixture setup

#### Scenario: Windows writes a temporary OpenSSH key

- **WHEN** release tests materialize an OpenSSH private key on Windows
- **THEN** the serialized key bytes are preserved exactly
- **AND** `ssh-keygen` can sign the checksum inventory

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `ci-diagnostics:Hosted fixtures are platform-default independent` | `1.1` | `tests/forge/test_forward_only.py::ProviderProjectionTests::test_divergent_github_tree_is_rejected_without_ref_change` |
| `ci-diagnostics:Hosted fixtures are platform-default independent` | `1.2` | `tests/release/test_assets.py::ReleaseAssetContracts::test_native_outputs_are_assembled_signed_and_verified_by_one_owner` |
