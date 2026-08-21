## 1. Repair ownership

- [x] 1.1 Remove native-supervisor mutation from the handoff child and verify focused CLI and protocol tests pass.
- [x] 1.2 Rebind and read back native supervision before listener handoff, then verify installation ordering, rollback, and unknown-outcome tests pass.
- [x] 1.3 Update the runtime-upgrade contract, architecture, governance, and Changelog to name the single transaction owner; verify strict OpenSpec validation passes.

## 2. Prove the product

- [x] 2.1 Run `uv run --locked --no-sync nox -s quick quality` and verify both sessions pass without warnings.
- [x] 2.2 Run `uv run --locked --no-sync nox -s tests-3.12 tests-3.13 tests-3.14` and verify the supported Python matrix passes.
- [x] 2.3 Run the complete macOS and Linux native release flows from the exact candidate tree and verify frozen install, handoff, teardown, and zero host residue.
- [ ] 2.4 Push one signed proposal commit and verify the hosted Windows Python matrix and native release flow pass on the exact product commit.

## 3. Publish and accept

- [ ] 3.1 Remove the failed `v2.0.53` tag from both Forges, archive this completed Change with strict validation, and mint one replacement signed commit and annotated tag.
- [ ] 3.2 Publish identical commit and tag objects plus complete macOS, Linux, and Windows assets to GitLab and GitHub; verify main, dev, tag CI, releases, manifests, and checksums.
- [ ] 3.3 Install the verified macOS asset and prove canonical service generation, listener health, ordinary and streaming Responses, provider switching, uninstall/reinstall, and zero test-host residue.
