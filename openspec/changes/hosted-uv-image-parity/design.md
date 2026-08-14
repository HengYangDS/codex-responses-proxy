# Design

`pyproject.toml` remains the sole UV version owner. GitLab image references
project that version into the two supported Python boundary images and retain
registry digests for immutable execution. The shell guard derives the same
version at runtime and emits one actionable mismatch diagnostic.

The existing `UV_PYTHON_INSTALL_DIR`, cache identity, and
`--python python --no-python-downloads` arguments remain intact. They keep
downloaded interpreters repository-local and ensure every Python tool executes
with the interpreter synchronized in the current job.
