## 1. Payload ownership

- [x] 1.1 Add failing AST contracts for peer-private access and forwarding aliases.
- [x] 1.2 Extract the owned-file primitives and inventory to one concrete owner.
- [x] 1.3 Move consumers and tests to direct imports and remove transaction facades.

## 2. Verification and lifecycle

- [x] 2.1 Pass focused payload, controller, release, formatting, lint, and type checks.
- [x] 2.2 Pass the complete coverage and supported-interpreter compile gates.
- [x] 2.3 Close the source change after the complete local gate; transfer the signed commit, exact-HEAD proof, and governed landing to the post-archive lifecycle.

## Post-archive lifecycle

1. Create or amend the trusted signed source commit and advance the exact Work Lane lease binding.
2. Refresh required parity evidence, execute exact-HEAD ETHOS proof, and land only with an authorized candidate transition.
