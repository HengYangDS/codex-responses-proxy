## Why

The Linux native build succeeds inside the GitHub job container, but the host-side artifact uploader resolves `runner.temp` to a different directory and falsely reports that no assets exist.

## What Changes

- Write the accepted Linux asset set to one workspace path visible to both the job container and host action.
- Upload from that exact path.
- Advance the forward-fix release to v2.0.29; preserve v2.0.28 as immutable failed evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: Require hosted native build output and artifact upload to preserve exact directory identity across container and host boundaries.

## Impact

GitHub verification workflow, its repository contract test, release metadata, and no production runtime code. GitLab remains an independent unchanged release plane.
