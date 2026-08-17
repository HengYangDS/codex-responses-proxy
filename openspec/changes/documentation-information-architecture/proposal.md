# Documentation Information Architecture

## Why

The Proxy documentation is intentionally small, but two content-bearing
documents still use the container name `README.md`. That convention obscures
their subjects and forces quality and release tools to preserve a naming
exception with no product value.

## What Changes

- Keep `docs/README.md` as the only documentation entry point.
- Rename the Decision Record register and evidence policy to semantic names.
- Update current documentation, agent entry points, quality checks, tests, and
  release metadata in the same atomic change.
- Retain the deliberately small domain tree; no empty category or redirect-only
  index is introduced.

## Capabilities

### Modified Capabilities

- `repository-organization`: make document names and repository checks express
  the same semantic information architecture.

## Boundaries

- No proxy runtime, provider, protocol, installation, release identity, or
  evidence taxonomy changes.
- No compatibility documents or duplicate paths remain.
- Historical archived OpenSpec records are not rewritten.
