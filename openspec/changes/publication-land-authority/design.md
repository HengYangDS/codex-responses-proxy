## Design

The defect is authority incompleteness, not a product behavior failure. The
single repair is to add `git.ref.compare-and-swap` to this Change's immutable
Commitment through the official rebind command. ETHOS continues to own the
exact-CAS operation; the repository gains no generic ref-update script.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `product-interface:Local product closure is Forge-free` | `1.1` | `ethos-land-readiness` |
