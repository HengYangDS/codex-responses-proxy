# Complete Rule Rationality

## Why

The architecture gate still mixed durable package topology with product-name and
syntax blacklists. Those rules encoded historical implementation details rather
than an observable proxy risk, creating false failures for legitimate adapters,
imports, and refactors.

## What Changes

- Keep one positive product-package topology, dependency graph, root-module
  boundary, package declaration contract, and cycle check.
- Move the package root and enforcement rationale into the machine policy.
- Remove named foreign-product literals and blanket private-symbol or forwarding
  alias bans.
- Remove whole-text path, identity, package-manager, and private-network scans;
  portability remains proven by native behavior, package isolation, and explicit
  configuration ownership.
- Remove Decision Record sequence contiguity while retaining unique identifiers,
  semantic names, required content, and canonical registration.
- Give commit grammar and deterministic text-layout gates the same explicit
  risk, measurement, false-positive, remediation, and review semantics.
- Delete the README sentence matcher; release validation keeps semantic release
  metadata and documentation links, not exact prose fragments.
- Reject unknown or incomplete policy schema instead of silently inventing
  checker defaults.

## Boundaries

This change does not alter proxy request handling, provider behavior, client
configuration, lifecycle semantics, releases, or Forge topology. It adds no
compatibility surface and no second policy owner.
