# Design

`pyproject.toml` already owns one digest-pinned Linux release runtime. The
native build uses it successfully, and the image contains Python, Git, OpenSSH,
curl, binutils, and tar. Publication therefore needs no mutable Debian package
transaction.

GitLab projects that runtime into both release jobs. The existing locked uv
bootstrap remains the only Python-tool bootstrap in the image, after which the
publisher executes through the synchronized interpreter exactly as before.
This deletes a networked setup phase without introducing a second image or
release path.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Release publication uses the immutable repository runtime` | `1.1` | `tests/forge/test_workflow_contracts.py` |
