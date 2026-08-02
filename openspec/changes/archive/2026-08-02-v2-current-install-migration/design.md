## Context

The v2.0.0 and current runtime inventories differ by one serving-module rename:
`codex_responses_proxy/replay/event.py` became
`codex_responses_proxy/replay/response.py`. Both use schema-2 manifests and the
same protocol-v2 entrypoint. The existing historical verifier recognizes only
pre-v2 schema-1/2 layouts, so it rejects the exact v2.0.0 file set.

## Decisions

### 1. Historical admission remains exact

The projection owner recognizes the complete v2.0.0 runtime file set, verifies
every manifest digest, serving aggregate, `VERSION`, canonical receipt, receipt
digest, receipt release, and the manifest-owned entrypoint. If finalized
install state exists, its schema, release, and receipt digest must also match.
Its absence is accepted only for this exact historical release shape because
the deployed v2.0.0 transaction reached serving before that final metadata file
was written. No subset, wildcard, or schema-only acceptance is introduced.

### 2. Retired files derive from verified inventory difference

Rollback records the exact files owned by the verified prior projection that
are absent from the candidate inventory. This includes the v2.0.0
`replay/event.py` path while retaining the existing rollback digest and
conflict checks. Snapshot metadata is derived from files that actually existed,
so rollback also restores the original absence of finalized install state.

### 3. The port remains configurable

`runtime.config.DEFAULT_PORT` is the single 8792 default. Installer/control/
uninstall CLI arguments and `CODEX_RESPONSES_PROXY_PROXY_PORT` remain the
configuration mechanisms. Production modules may reference the named owner,
not copy either 8791 or 8792 literals.

## Migration Plan

1. Prove focused RED for the current default and exact v2.0.0 projection.
2. Implement the minimum exact-inventory and default-owner changes.
3. Prove rollback, quality, Python 3.12-3.14, OpenSpec, and release metadata.
4. Publish a new immutable patch release and install it on the configured 8792
   runtime through the existing protocol-v2 transaction.

Rollback uses the preceding signed release and never changes Codex history.
