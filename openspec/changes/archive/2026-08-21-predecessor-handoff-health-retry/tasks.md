## 1. Reproduce and repair

- [x] 1.1 Reproduce the official `2.0.52` to `2.0.53` failure on an isolated
  install root, service identity, state root, and loopback port.
- [x] 1.2 Add a failing regression for transient HTTP protocol reads and extend
  the existing bounded observer without a parallel retry path.

## 2. Prove and release

- [x] 2.1 Run focused handoff tests and the quick quality gate.
- [x] 2.2 Build the native candidate and pass published-predecessor compatibility.
- [x] 2.3 Run full quality, test, release, and strict OpenSpec gates.
- [x] 2.4 Archive the verified source Change.

## Delivery boundary

Dual-Forge publication, formal installed-runtime upgrade, and residue-free
teardown remain post-archive delivery effects. They require fresh external
evidence and are not asserted by this source archive.
