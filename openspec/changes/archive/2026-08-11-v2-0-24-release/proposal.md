# Release v2.0.24

## Why

The accepted source already contains the terminal handoff and provider-portable
reliability repairs. This forward-only patch release packages that exact source
for independent GitLab and GitHub publication without rewriting v2.0.23.

## What Changes

- advance the single release identity in `VERSION` to `2.0.24`;
- align the current Changelog and installation examples with that identity;
- prove and land the resulting exact source tree before any external delivery.

## Capabilities

This is a release, documentation, and verification change only; it introduces no
new runtime capability and therefore intentionally skips a spec delta.

## Impact

Only release metadata, user-facing documentation, and OpenSpec lifecycle
artifacts change. Publication, installation, runtime acceptance, and lane-family
retirement follow after accepted closeout and require fresh external evidence.
Provider routing, replay projection, backpressure, native supervision, and
client/session storage boundaries remain unchanged.
