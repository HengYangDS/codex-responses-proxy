## Context

GitHub 2.0.12 failed on Windows filesystem-mode projection, Linux listener
inspection, controller-disconnect sequencing, and uv hardlink warnings. These
are independent symptoms of host state leaking into product verification.

## Goals / Non-Goals

**Goals:**

- Make process and listener inspection a bundled cross-platform capability.
- Transfer transaction ownership before the acknowledgement can fail.
- Keep Git intent and host filesystem capabilities separate.
- Keep successful CI output warning-free.

**Non-Goals:**

- Changing provider protocol behavior or AIGW configuration.
- Weakening exact executable/role identity, coverage, or failed-release history.
- Restarting the installed 2.0.10 runtime before a verified release exists.

## Decisions

1. Use `psutil` as one mature product dependency for process command lines,
   process inventory, listener connections, and termination. This deletes
   platform subprocess parsing and removes `lsof`, `ps`, PowerShell CIM, Darwin
   `sysctl`, and Windows argv parsing as competing owners. The rejected option
   is adding `lsof` only in CI, which would hide the product defect.
2. Start the daemon commit coordinator immediately after READY preparation,
   before writing HTTP 202. The response is observational; ownership already
   belongs to the listener. A write failure is ignored only at this post-READY
   boundary.
3. Read the pre-commit mode from `git ls-files --stage`; executable intent is
   repository metadata, not a Windows filesystem feature.
4. Set `UV_LINK_MODE=copy` in the shared deterministic test environment so both
   bootstrap and Nox child installs use one warning-free policy.

## Risks / Trade-offs

- **New binary dependency** → lock one stable psutil release and prove the wheel
  and PyInstaller executable on all three native platforms.
- **Coordinator starts before acknowledgement** → keep prepare fully complete
  first and test exactly-once start for successful and broken writes.

## Migration Plan

Run focused red-green tests, then quick, quality, Python 3.12-3.14, native
release, strict OpenSpec, and exact-HEAD proof. Archive and land only after all
pass; publish 2.0.13 forward without modifying 2.0.12 records.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Hosted verification uses portable product semantics` | `1.1` | `tests/governance/test_repository.py` |
| `product-interface:Native lifecycle inspection is self-contained` | `1.2` | `tests/lifecycle/supervision/test_process.py` |
