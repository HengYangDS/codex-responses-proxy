## Why

GitLab synchronized the locked environment against `python`, then allowed
`uv run` to select another interpreter. The publish job consequently ran
without the installed product dependency `cyclopts`.

The same runner also cached package downloads but not UV-managed Python
runtimes, making empty-runner matrix duration unnecessarily variable.

## What Changes

- Bind every GitLab post-sync execution to the exact `python` identity.
- Disable implicit Python downloads during those executions.
- Cache UV-managed Python runtimes under a target-platform cache identity.
- Express the behavior through focused positive workflow contracts.

## Boundary

This Change modifies GitLab verification and publication execution only. It
does not change product runtime behavior, release contents, GitHub authority,
or any foreign Work Lane.
