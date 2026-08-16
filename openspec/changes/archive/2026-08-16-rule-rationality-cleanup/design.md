# Design

## One Structural Owner

`quality-boundaries` owns package topology, dependency direction, public
documentation, root-module placement, and descriptive source observations.
`ci-diagnostics` continues to own verification composition, coverage, and
hosted execution, but no longer duplicates repository-structure policy.

## Admission Model

| Class | Merge authority | Required basis |
| --- | --- | --- |
| Semantic invariant | Blocking | Exact ownership, dependency, portability, or public-contract failure |
| Risk threshold | Blocking only when admitted | Risk model, exact unit, false-positive cost, repair path, review condition |
| Review heuristic | Non-blocking | Descriptive evidence only |
| Historical ratchet | Temporary | Named debt and explicit exit condition |

The positive `allowed_package_edges` graph rejects undeclared packages and
invalid dependencies. A separate negative package-name list is unnecessary and
can drift from that graph.

## Lean Implementation

The checker keeps AST traversal needed for public docstrings and descriptive
inventory. It deletes all threshold comparison, ratchet parsing, and exception
logic. Retired policy keys are not accepted through a compatibility surface.

## Verification

Contract tests prove that undeclared packages, invalid edges, root behavior,
private cross-package imports, forwarding facades, and missing public docs still
fail. A deliberately large source owner proves metrics remain observable but do
not independently veto a change. The complete quality session proves behavior,
coverage, types, formatting, documentation, governance, and release contracts.
