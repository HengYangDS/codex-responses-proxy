# Windows Native Bundle Forward Fix

## Why

v2.0.18 preserved the case-insensitive identity intent but failed the real
Windows matrix because `commonpath` reintroduced Windows separators after the
inputs were normalized. A POSIX symlink fixture also executed under incompatible
Windows symlink semantics.

## What changes

- compare the normalized `commonpath` result with the normalized bundle path;
- keep POSIX symlink materialization and escape checks on compatible hosts;
- publish v2.0.19 without rewriting the failed v2.0.18 evidence.
