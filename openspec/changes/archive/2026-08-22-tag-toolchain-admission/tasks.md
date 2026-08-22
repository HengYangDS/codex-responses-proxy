## 1. Reproduce and repair

- [x] 1.1 Add a workflow-contract regression requiring the tag-governance job to install the repository projection toolchain, and verify that it fails against the current generated workflow.
- [x] 1.2 Add the existing pinned `mise` action to the provider-neutral tag-governance graph, regenerate Forge projections, and verify the focused contract passes.

## 2. Validate and deliver

- [x] 2.1 Run OpenSpec strict validation and the smallest affected governance gate with warning-free output.
- [x] 2.2 Archive the completed change and create a signed forward-fix commit.
- [ ] 2.3 Verify the release tag pipeline succeeds before publication resumes.
