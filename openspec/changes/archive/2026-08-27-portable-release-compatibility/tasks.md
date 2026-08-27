## 1. Correct the portable test model

- [x] 1.1 Reuse production executable and command-path projection in the native
      lifecycle fixture and verify the Windows projection regression passes.
- [x] 1.2 Admit both the exact draining predecessor and exact accepting
      successor as request-release points and verify the focused regression
      passes.

## 2. Verify and close the source change

- [x] 2.1 Pass strict OpenSpec validation and the repository quick gate without
      warnings.
- [x] 2.2 Archive this completed source change after its focused regressions and
      local gates pass.

## Post-archive lifecycle

Create one signed Conventional Commit successor and run exact-HEAD proof. Update
the same proposal on both Forges. After all required checks pass, merge the
unchanged commit to `dev`, remove both proposal branches, advance `main` through
the declared release path, and publish and install the verified release.
