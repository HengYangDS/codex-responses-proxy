## Why

Both hosted verification planes exposed bootstrap assumptions that local Nox
sessions did not exercise. GitHub ran a repository module before installing its
locked dependencies. GitLab invoked the `pytest` console script under importlib
mode, which removed the repository root needed by repository-only `tools`
modules.

## What Changes

- Install the locked quality environment before GitHub reads the Python matrix.
- Execute the matrix owner and GitLab tests with `python -m` so module resolution
  follows the selected interpreter.
- Make both contracts executable before publication.

## Boundary

This Change only repairs hosted verification bootstrap. It does not change the
product runtime, provider protocol, release identity, or Forge independence.
