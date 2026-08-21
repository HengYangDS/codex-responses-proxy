## 1. Reproduce and repair

- [x] 1.1 Reproduce the official `2.0.52` CLI upgrading the current candidate.
- [x] 1.2 Make that predecessor-driven path the permanent compatibility test.
- [x] 1.3 Bootstrap a missing carrier only for the handoff child and reject a
  partial predecessor environment.

## 2. Prove and release

- [x] 2.1 Pass focused runtime-context and CLI composition tests.
- [x] 2.2 Pass real published-predecessor native compatibility.
- [x] 2.3 Pass quick, quality, Python 3.12/3.13/3.14, release, and strict
  OpenSpec gates.
- [x] 2.4 Archive the verified source Change.

## Delivery boundary

Dual-Forge publication, canonical `8792` upgrade, runtime operations, and the
immediate successor Change that deletes the bridge are post-archive delivery
effects. They consume this verified source and do not become circular source
acceptance prerequisites.
