# Design

## Reproducible Linux Asset

PyInstaller remains the release owner. A standard analysis hook sets
`module_collection_mode = "py"` for `ctypes`, so that module is collected as
source rather than serialized into `PYZ.pyz`. This removes the proven marshal
identity variance without a custom archive format or post-build rewriter.

## Exact Successor Prewarm

`lifecycle.transaction` writes and verifies the admitted projection, then asks
`lifecycle.candidate` to run `version` on `RuntimeContext.executable`. A failed
probe remains inside the existing transaction rollback boundary. No temporary
payload copy or second installed-state authority remains.

## One Startup Deadline

The installation timeout is the single readiness budget. The controller sends
that value to the listener and allows the same value for the HTTP exchange,
with one second reserved for transport completion. Listener convergence and
rollback remain separately bounded by their existing protocol leases.

## Verification

TDD pins hook integration, exact-path prewarm ordering, and removal of the
ten-second cap. Two clean builds in the same locked Linux environment must
produce identical executable and archive hashes before release.
