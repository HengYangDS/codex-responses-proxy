# Clean hosted CI diagnostics

## Why

Successful hosted verification emits Git initialization hints and concurrent
`setup-uv` cache reservation warnings. These messages hide actionable failures
and make green jobs appear unhealthy.

## What changes

- declare `main` as Git's process-scoped default branch;
- isolate macOS Python-matrix caches by interpreter;
- enforce both properties in the existing workflow contract.

## Non-goals

- no runtime, provider, release, runner, or Forge-topology behavior changes;
- no global Git configuration and no diagnostic suppression.
