## 1. Protocol correction

- [x] 1.1 Add a regression from the Codex 0.151.0 namespaced
  `function_call_output` shape and verify it fails with
  `unknown_output_field` before the implementation changes.
- [x] 1.2 Admit only the documented `namespace` metadata while preserving the
  existing portable output form and exact unknown-field rejection; verify the
  focused request-projection tests pass.
- [x] 1.3 Set the immutable patch release identity to `3.1.9`, record the
  correction in the Changelog, and verify the metadata contract.

## 2. Acceptance

- [x] 2.1 Pass strict OpenSpec validation, the affected protocol and relay
  suites, Python quality, and the repository release gate.
