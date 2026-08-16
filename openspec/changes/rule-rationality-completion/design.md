# Design

## Admission Principle

A blocking rule protects an observable product risk through one satisfiable
contract. Package ownership and dependency direction are durable; names of
foreign products and implementation syntax are not.

| Retained contract | Protected risk | Measurement |
| --- | --- | --- |
| Declared package set | Ambiguous semantic ownership | Direct children of the declared product package |
| Allowed dependency edges | Hidden coupling and non-local changes | Parsed absolute package imports |
| Root implementation boundary | Product behavior outside the package | Repository-root Python modules against the declared configuration set |
| Package declarations | Undiscoverable package purpose | `__init__.py` module docstrings |
| Acyclic dependency graph | Mutually dependent owners | Strongly connected components in the observed package graph |
| Commit grammar | Unsearchable and automation-hostile history | Parsed subjects against the tracked positive grammar |
| Deterministic text layout | Cross-host byte and diff drift | UTF-8, LF, final-newline, and trailing-whitespace checks |

## Removed Negative Surfaces

The checker no longer infers architecture from a named foreign product, a
private symbol, or an assignment that forwards another module's value. Those
constructs may be valid or invalid depending on the positive owner and dependency
contract; syntax alone is not a merge decision.

The release path also stops matching a particular README sentence. Product
identity is already owned by package metadata and the README title; Forge
independence is owned by release behavior and its canonical governance
contract. Exact explanatory prose is documentation, not executable policy.

## Single Sources

- `.config/checks/architecture/policy.toml` owns the product package, dependency
  graph, root modules, inventory roots, and rationale.
- `.config/checks/commits/policy.toml` owns commit grammar and its rationale.
- `.config/checks/text-layout/policy.toml` owns deterministic text bytes and its rationale.
- `tools/quality/architecture.py` strictly interprets that schema.
- OpenSpec describes observable behavior and does not duplicate executable
  topology values.
