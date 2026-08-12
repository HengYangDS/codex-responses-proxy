## Context

Quality and release used one dependency group, so hosted verification fetched a
large native packager it never executed. GitLab also inherited the runner host's
container architecture unless each job happened to override it.

## Decision

Use two lock-derived dependency groups: `quality` for verification and
`release` for PyInstaller. Nox defaults to `quality`; its release session asks
for both groups explicitly. GitLab installs only `quality` outside the native
build job and declares `linux/amd64` once in the default image contract, with
the floor and release images retaining explicit platform declarations.

## Rejected Alternatives

- Retrying the same pipeline: preserves the unnecessary download and ambiguous
  platform evidence.
- Installing all groups everywhere: increases failure surface without proving
  more product behavior.
- Adding runner-host conditionals: couples repository truth to one workstation.
