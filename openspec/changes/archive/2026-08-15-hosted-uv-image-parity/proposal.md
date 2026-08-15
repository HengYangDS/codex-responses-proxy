# Hosted UV Image Parity

## Why

GitLab's Python images name the supported interpreter but do not bind the UV
binary to the version owned by `pyproject.toml`. A floating image can therefore
start with a different UV release and fail before the repository gates run.

## What Changes

- Bind both GitLab UV images to the repository-owned UV version and immutable
  image digests.
- Report the expected and observed UV versions when the executable contract
  fails.
- Preserve the repository-local Python install directory and the explicit
  synchronized-interpreter execution contract.

## Non-goals

- Changing the supported Python matrix, dependency lock, release version, or
  GitHub publication workflow.
