## 1. Dependency convergence

- [x] 1.1 Audit the declared Python toolchain against current stable releases.
- [x] 1.2 Advance the existing `ty` declaration and regenerate `uv.lock`.
- [x] 1.3 Confirm the diff adds no package, wrapper, compatibility layer, or
  alternate dependency authority.

## 2. Verification

- [x] 2.1 Run the repository `quick` session.
- [x] 2.2 Run the repository `quality` session and prove statement, branch, and
  aggregate coverage remain strictly above 95 percent.
- [x] 2.3 Run the complete Python 3.12, 3.13, and 3.14 matrix.
- [x] 2.4 Build and black-box test the native release asset.
- [ ] 2.5 Execute exact-HEAD ETHOS proof, archive the Change, and land through
  the public lifecycle.
