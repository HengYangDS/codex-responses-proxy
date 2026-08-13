# GitLab UV Version Contract

## Why

Official UV images append platform information to `uv --version`. Comparing
that human-facing line verbatim makes every GitLab gate fail before tests run.

## What Changes

- Compare only UV's machine version token with the version owned by
  `pyproject.toml`.
- Exercise the exact GitLab shell fragment with suffixed and mismatched output.

## Non-goals

- Changing the required UV version, images, product runtime, or release format.
