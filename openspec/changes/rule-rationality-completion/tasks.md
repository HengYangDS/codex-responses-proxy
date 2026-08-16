## 1. Contract

- [x] 1.1 Record one explicit rationale for the blocking architecture policy.
- [x] 1.2 Restate architecture admission as positive topology and package contracts.

## 2. Implementation

- [x] 2.1 Declare the product package root in the policy.
- [x] 2.2 Remove named-product, private-symbol, and forwarding-alias blacklists.
- [x] 2.3 Remove whole-text portability scans while retaining native and package-isolation proof.
- [x] 2.4 Remove Decision Record sequence contiguity while retaining identity and registration.
- [x] 2.5 Reject unknown or incomplete policy schema.
- [x] 2.6 Delete obsolete implementation and tests without compatibility parsing.
- [x] 2.7 Add explicit rationale to commit and text-layout policies.
- [x] 2.8 Delete exact README prose matching from quality and release validation.

## 3. Verification

- [ ] 3.1 Pass focused architecture tests and strict OpenSpec validation.
- [ ] 3.2 Pass the locked repository quality graph and Python matrix.
- [ ] 3.3 Produce exact-HEAD proof for the signed atomic result.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `quality-boundaries:one structural quality boundary` | `2.1`-`2.6` | `focused-architecture-and-quality` |
