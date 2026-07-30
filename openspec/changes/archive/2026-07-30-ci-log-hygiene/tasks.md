## 1. Diagnose

- [x] 1.1 Verify the `v1.0.35` GitLab and GitHub job states and inspect their logs.
- [x] 1.2 Attribute the traceback, Python warning, and pip warning to their owners.

## 2. Repair

- [x] 2.1 Close caught production HTTP errors explicitly.
- [x] 2.2 Bound expected peer-disconnect handling to the loopback fixture.
- [x] 2.3 Make the canonical runner reject leaked diagnostics and isolate compilation.
- [x] 2.4 Align both Forge projections, tests, docs, VERSION, and CHANGELOG.

## 3. Verify

- [x] 3.1 Run Ruff, types, structure, docstrings, and the 95% coverage floor.
- [x] 3.2 Run the Python 3.12, 3.13, and 3.14 compile-and-test matrix.
- [x] 3.3 Run release and provider-projection contracts.
- [x] 3.4 Scan every captured verification log for forbidden diagnostics.

## 4. Close out

- [x] 4.1 Complete strict OpenSpec validation before exact-HEAD ETHOS proof.
- [x] 4.2 Archive the locally proven change through the official OpenSpec
  transition. Candidate landing and Work Lane retirement are repository
  lifecycle transitions; Forge publication, installation, runtime acceptance,
  and repository-family records remain external states owned by their respective
  release operations rather than this change checklist.
