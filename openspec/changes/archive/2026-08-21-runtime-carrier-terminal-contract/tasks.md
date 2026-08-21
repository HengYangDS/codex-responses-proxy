## 1. Retire the migration bridge

- [x] 1.1 Remove environment-derived carrier materialization and verify every private role invokes the same strict activation call.
- [x] 1.2 Delete bridge-only tests and retain positive missing-carrier plus current-forward-upgrade coverage; verify focused CLI, runtime-context, and native compatibility tests pass.

## 2. Prove and archive the terminal contract

- [x] 2.1 Set release identity to `2.0.56`, document the retired migration without preserving instructions, and pass strict OpenSpec validation.
- [x] 2.2 Pass quick, quality, Python 3.12/3.13/3.14, native release, and warning-free gates.
- [x] 2.3 Prove no bridge-only source, fixture, documentation, or CI consumer remains and archive the completed source Change.

## Delivery boundary

Dual-Forge publication and formal `8792` upgrade consume the archived, signed
source. Their receipts are external delivery evidence; they do not keep a
completed source Change active or make source acceptance depend on publication.
