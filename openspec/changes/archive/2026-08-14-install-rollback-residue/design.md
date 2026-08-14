# Design

## Decision

The transaction already owns the immutable candidate blob inventory. Pass that
inventory to the rollback owner, which combines it with the prior owned
inventory and subtracts every path present in the retained snapshot.

```text
remove = (prior-owned ∪ candidate-paths) − prior-present
restore = prior-present
preserve = everything outside candidate-paths and prior-owned
```

This keeps one authority for each fact: the snapshot owns prior state and the
transaction owns candidate state. No directory-wide deletion or compatibility
layer is introduced.

## Safety

- Paths remain canonical and symlink-safe through `owned_files`.
- Unknown content is outside the removal set and remains untouched.
- A candidate collision with unknown content is rejected before mutation.
