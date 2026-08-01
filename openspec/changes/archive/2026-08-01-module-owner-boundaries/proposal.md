## Why

The payload package had been split physically while peer modules still reached
through `projection` private symbols and `transaction` forwarded symbols owned
by `state`, `inventory`, or `digest`. The directory shape therefore overstated
the real module boundaries and made tests depend on indirect authorities.

## What Changes

- Give symlink-safe owned-file paths and I/O one explicit `owned_files` owner.
- Make payload modules and consumers import their concrete owners directly.
- Remove forwarding aliases and cross-module private access from the payload
  package.
- Add AST regression checks for both forbidden forms.

## Impact

This is an internal refactor with no CLI, wire, provider, installation, or
release-format change. Runtime behavior remains covered by the existing
transaction, migration, controller, and released-source tests.
