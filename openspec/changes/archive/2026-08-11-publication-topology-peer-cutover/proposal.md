# Declare publication peers

## Why

The repository still encoded GitLab and GitHub as four provider-specific
publication scalars. The adopted ETHOS runtime accepts one peer collection and
intentionally has no compatibility reader for the retired fields.

## What changes

- declare GitLab and GitHub as independent publication peers;
- retain one local verification and installation contract;
- make the repository contract reject parallel legacy fields.

## Non-goals

- no Forge push, tag, Release, or installation effect;
- no compatibility aliases or inferred default peer;
- no change to provider traffic or client configuration.
