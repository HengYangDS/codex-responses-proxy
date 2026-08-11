# Scope Git trust to the GitHub workspace

## Why

The v2.0.26 GitHub Linux container runs as a different user from the checkout
owner. Git therefore rejects `git archive HEAD` before the release build starts.

## What changes

- authorize only the exact `GITHUB_WORKSPACE` for the archive command;
- reject wildcard or persistent Git trust configuration;
- release the repair as v2.0.27 without rewriting v2.0.26 history.

## Boundaries

The source tree, release runtime, GitLab pipeline, provider routing, installed
service, and Codex conversation state are unchanged.
