## 1. Authority inventory

- [x] 1.1 Inventory every Claim and Chronicle and resolve its canonical history carrier.
- [x] 1.2 Inspect Chronicles not selected by a Claim for unique semantics.

## 2. Destructive convergence

- [x] 2.1 Delete the tracked evidence root and family policy.
- [x] 2.2 Delete Claim and Chronicle consumers, tests, and naming exemptions.
- [x] 2.3 Rewrite the canonical policy and specification around one authority chain.

## 3. Verification and closeout

- [x] 3.1 Pass focused tests and complete repository quality gates.
- [x] 3.2 Commit and run exact-HEAD proof before archiving the Change.
- [x] 3.3 Authorize archive, post-archive proof, integration, and lane retirement.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `evidence-layout:Current evidence has one authority chain` | `2.1` | `quick` |
| `evidence-layout:Forge comparison has one semantic owner` | `2.3` | `quick` |

## Delivery boundary

Exact-HEAD proof, Change archive, candidate integration, accepted and release
closeout, hosted CI, publication, installation, and lane retirement remain
separate lifecycle effects.
