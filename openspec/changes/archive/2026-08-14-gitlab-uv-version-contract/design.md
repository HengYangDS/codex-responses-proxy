# Design

Use POSIX parameter expansion to remove the stable `uv ` prefix and any
subsequent display suffix. This keeps `pyproject.toml` as the sole version
owner and adds no parser, wrapper, dependency, or parallel configuration.
