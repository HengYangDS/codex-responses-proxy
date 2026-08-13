# GitHub Windows POSIX Test Boundary

## Why

The GitLab version contract is a POSIX shell fragment. Executing that fragment
on Windows incorrectly requires `/bin/sh` and fails before testing product code.

## What Changes

- Keep structural inspection of the GitLab workflow in every platform matrix.
- Execute the POSIX shell fragment only where POSIX `sh` is part of the target
  contract.

## Non-goals

- Adding a shell to Windows, reducing Windows product coverage, or changing
  runtime behavior.
