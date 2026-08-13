# Refresh the locked Python quality toolchain

## Why

The committed quality toolchain trails the current stable `ty` release and its
resolved Python-discovery dependency. Keeping stale pins adds maintenance cost
without preserving any product contract.

## What Changes

- Advance `ty` to `0.0.71`.
- Regenerate `uv.lock`, admitting `python-discovery` `1.5.2` as the resulting
  transitive resolution.

## Capabilities

No product capability changes. This Change only updates the existing dependency
declaration and lock authorities.

## Impact

`pyproject.toml` remains the direct dependency SSOT and `uv.lock` remains the
only transitive-resolution SSOT. Runtime behavior, provider semantics, Python
support, release identity, and Forge topology do not change.
