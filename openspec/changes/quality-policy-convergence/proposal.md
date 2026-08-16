# Converge Quality Policy

## Why

Proxy coverage admission had two threshold owners and treated volatile
file-sized ratios as equivalent to product aggregate and semantic-package risk.
That encouraged denominator-driven tests and duplicated policy across TOML,
INI, implementation, tests, and specifications.

## What Changes

- Keep aggregate and semantic-package statement and branch evidence as the
  blocking coverage boundary.
- Remove file/module-level coverage vetoes.
- Make `.config/checks/coverage/policy.toml` the sole floor owner; keep
  `coverage.ini` limited to coverage.py collection and rendering behavior.
- Record the risk model, measurement, false-positive cost, remediation path,
  and review condition beside the floor.

## Boundaries

This change does not alter request handling, provider behavior, retry or
backpressure policy, process ownership, installation, release identity, or
supported platforms. It adds no compatibility path and no second policy file.
