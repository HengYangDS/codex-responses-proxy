## Context

The native Darwin reader already isolates `ctypes` calls behind
`_darwin_process_argv`. A real Darwin subprocess proves host integration, while
mocked `find_library`, `CDLL`, and `sysctl` calls can prove byte decoding without
calling a Linux libc symbol that does not exist.

## Goals / Non-Goals

**Goals:**

- Make the successful Darwin argv branch deterministic on Linux, macOS, and
  Windows test hosts.
- Preserve the real Darwin integration test and its platform guard.
- Restore hosted branch coverage above the repository floor without excluding
  production lines from measurement.

**Non-Goals:**

- Change process discovery or supervision behavior.
- Lower, round, combine, or waive the 95 percent branch floor.
- Rewrite or delete failed release history.

## Decisions

Use a small synthetic `sysctl` double that returns one valid
`kern.procargs2` payload. This tests the same parsing owner on every host without
mocking `sys.platform` or entering real foreign libc. Moving native parsing into
a second implementation or using coverage exclusions would duplicate semantics
or hide the gap.

Treat `v2.0.6` as immutable failed publication evidence and advance to
`v2.0.7`. Existing tags cannot be repaired in place.

## Risks / Trade-offs

- [Synthetic payload diverges from Darwin layout] -> retain the real Darwin
  subprocess integration alongside the portable contract.
- [Local macOS coverage masks Linux drift again] -> require hosted Linux CI and
  the existing 3.12-3.14 matrix before installation.
