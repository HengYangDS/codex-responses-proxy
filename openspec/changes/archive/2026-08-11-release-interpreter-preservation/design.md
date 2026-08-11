## Decision

Use `sys.executable` exactly as supplied by the running process. A virtual
environment is an execution boundary, not an alias to normalize.

## Rejected

- installing release dependencies into the host interpreter;
- bypassing release metadata validation;
- rewriting the failed v2.0.24 tag or runs.
