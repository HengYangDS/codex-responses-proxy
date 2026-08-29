## Context

The predecessor resolver writes the exact tag to `GITHUB_ENV`. The following
step currently dereferences it as `$NAME`, which is valid in POSIX shells but
not in PowerShell.

## Goals / Non-Goals

**Goals:**

- Preserve one predecessor resolver and one downloader invocation.
- Make tag consumption independent of the runner shell.

**Non-Goals:**

- Add a wrapper, downloader, compatibility layer, or platform branch.
- Change predecessor selection or release asset semantics.

## Decisions

Use GitHub Actions expression interpolation for the value written to
`GITHUB_ENV`. GitHub resolves this before invoking the runner shell, so the
existing command remains identical on macOS, Linux, and Windows. A Python
downloader or shell-specific branch would add a second implementation without
adding product capability.

## Risks / Trade-offs

- **Expression context is unavailable** -> The existing resolver and contract
  test bind the value before the download step, and hosted CI provides the final
  platform proof.
