## Context

The Linux gate missed one Darwin state-root branch and one malformed native-
argument rejection branch. Both are pure functions behind injectable platform
or `ctypes` boundaries, so a foreign operating-system call is unnecessary.

## Goals / Non-Goals

**Goals:**

- Make both outcomes deterministic on Linux, macOS, and Windows.
- Keep hosted statement and branch coverage strictly above 95 percent.

**Non-Goals:**

- Change runtime behavior or add a second implementation.
- Exclude lines, lower the floor, or rewrite failed tags and jobs.

## Decisions

Extend the existing table-driven path test with the Darwin defaults and extend
the existing synthetic Darwin payload test with one incomplete argument vector.
This tests the semantic owners directly and avoids host spoofing around a real
foreign libc call.

## Risks / Trade-offs

- [Synthetic data drifts from native layout] -> retain the real Darwin process
  integration and use the same established synthetic wire builder.
- [Local evidence masks hosted drift] -> require a clean Linux 3.12 quality run
  and both Forge main gates before tagging.
