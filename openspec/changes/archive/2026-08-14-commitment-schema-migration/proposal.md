# Migrate the repository Commitment schema

## Why

The accepted repository Commitment carries retired permission fields. The
current ETHOS runtime therefore cannot compile a governed plan.

## What changes

- migrate the repository Commitment to the current schema;
- add the canonical OpenSpec entrypoint;
- preserve product behavior and repository authority.

## Non-goals

- no proxy, provider, release, or runtime behavior changes;
- no compatibility layer or duplicate authority surface.
