# Reproducible native release assets

## Why

The independent v2.0.25 GitLab and GitHub Linux builders produced valid but
different archives. They selected different Python patch releases and retained
checkout paths and installer timestamps inside the native payload.

## What changes

- define one repository-owned exact runtime for Linux release builds;
- execute both Forge Linux builders in that immutable runtime;
- exclude installer provenance that is not required at runtime;
- prove byte parity from separate checkout roots;
- release the repair as v2.0.26 without rewriting v2.0.25 history.

## Boundaries

Each Forge still builds, signs, publishes, and verifies its own release. Neither
Forge consumes artifacts, credentials, APIs, or state from the other. Runtime
behavior, provider routing, client configuration, and Codex conversation state
are unchanged.
