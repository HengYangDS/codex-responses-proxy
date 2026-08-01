# ADR-0001: Keep AIGW Control Plane Separate from Proxy Data Plane

- Status: amended
- Date: 2026-07-14

## Context

AIGW projects provider configuration across Codex profiles. The proxy provides
local Responses replay compatibility and a loopback service. Letting both write
the same configuration or manage each other's lifecycle causes drift, unsafe
recovery, and ambiguous rollback responsibility.

## Decision

AIGW owns marked provider blocks, credentials, endpoint selection, and
configuration projection. Codex Responses Proxy owns outbound replay sanitization,
its executable payload, and its listener/watchdog lifecycle. The installed
proxy is generated from source and verified with a manifest. The proxy never
writes an AIGW-owned configuration file. An explicitly adopted
compatibility route may ask AIGW's public CLI to change its canonical endpoint
and must verify the result.

## Consequences

The systems can evolve independently and each has one owner for its mutations.
Runtime repair is performed by rebuilding the proxy projection or using AIGW's
atomic sync path; no session-history mutation is permitted.
