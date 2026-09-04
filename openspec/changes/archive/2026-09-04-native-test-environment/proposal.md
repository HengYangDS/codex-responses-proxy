## Why

Native executable tests currently replace the child-process environment with
only `HOME` and `PATH`. That artificial environment removes operating-system
runtime variables such as Windows `SystemRoot`, so a valid release executable
fails before the product starts.

## What Changes

- Derive native test environments from the current host environment.
- Override only the isolated home, product roots, and command search path owned
  by each test.
- Preserve production behavior and the existing no-Python-on-`PATH` guarantee.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: native executable verification preserves the host
  operating-system runtime environment while isolating product-owned paths.

## Impact

The change is limited to the native executable contract tests and their product
interface requirement. It adds no production abstraction, dependency, or
compatibility layer.
