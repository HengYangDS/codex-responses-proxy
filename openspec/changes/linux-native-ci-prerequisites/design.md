## Context

See `proposal.md`. Both the Python matrix and Python quality jobs build the
same native executable through Nox on `python:<minor>-slim`; neither image
guarantees the external binary inspection tool required by PyInstaller.

## Goals / Non-Goals

**Goals:**

- Make the Linux prerequisite explicit at the thinnest provider projection.
- Keep the repository lock and Nox session graph as the sole Python toolchain
  and verification owner.
- Reject future removal through a focused textual CI contract.

**Non-Goals:**

- Moving operating-system packages into Python metadata.
- Binding CI to the current self-hosted runner or container cache.
- Weakening native executable acceptance on any Python line.

## Decisions

Install Debian `binutils` in the two GitLab `before_script` blocks that invoke
native builds. This is an operating-system prerequisite, not a Python project
dependency, so `pyproject.toml`, `uv.lock`, and Nox remain unchanged. A custom
container image was rejected because it would introduce another maintained
artifact and hide rather than declare the dependency. Skipping PyInstaller in
matrix or quality jobs was rejected because it would narrow the accepted gate.

## Risks / Trade-offs

- **Package bootstrap adds a small CI cost** -> use the distribution package
  and retain `--no-install-recommends`.
- **Another base distribution names the tool differently** -> the current
  projection explicitly selects Debian slim images; another projection must
  declare its own equivalent prerequisite.

## Migration Plan

Commit the projection and contract together, run exact-head local proof, land
forward-only, and require a new GitLab main pipeline. Revert the commit if the
declared package does not provide `objdump`; do not bypass native builds.
