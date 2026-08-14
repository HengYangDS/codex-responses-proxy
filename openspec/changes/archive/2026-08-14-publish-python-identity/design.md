## Context

`uv sync --python python` creates one selected environment. An unqualified
subsequent `uv run --no-sync` may choose a different interpreter identity and
therefore a different environment. Cache identity based on the runner binary
architecture also describes the host rather than the declared container
target.

## Decision

GitLab uses one explicit execution contract after locked synchronization:

```text
uv run --locked --no-sync --python python --no-python-downloads
```

The shared cache contains both package data and `UV_PYTHON_INSTALL_DIR`; its
key names the declared Linux amd64 CI target. `uv.lock` and project metadata
remain the dependency and bootstrap authorities.

## Rejected Alternatives

| Alternative | Reason |
| --- | --- |
| Increase the job timeout | Hides environment drift and preserves cold runtime downloads. |
| Install `cyclopts` separately | Creates a parallel dependency authority. |
| Use an ambient interpreter | Reintroduces runner-dependent behavior. |
