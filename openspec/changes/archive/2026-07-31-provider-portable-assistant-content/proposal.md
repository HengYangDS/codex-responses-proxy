## Why

The unchanged original conversation exposed a release-blocking gap after
v1.0.43 installation: historical assistant content was projected as
`input_text`, and the DMXAPI Responses validator rejected it because assistant
output content accepts `output_text` or `refusal`. Existing tests had encoded
the same role-agnostic normalization and therefore did not protect the live
contract.

## What Changes

- Project textual assistant and synthesized-agent history as the provider-neutral
  Easy Input Message string form, while system, developer, and user dialogue
  continues to use input content.
- Preserve assistant refusal text without retaining provider-bound output-item
  identity, status, annotations, or typed output blocks; keep
  function/custom-tool output payloads on their input-content grammar.
- Keep the DMX classified-empty-response fallback on the same role-aware
  grammar instead of undoing the normal outbound projection during its one
  bounded retry.
- Add regression tests reproducing the exact rejected assistant shape before
  changing production code, then rerun the complete supported Python matrix.
- Release the correction as v1.0.44 and return unchanged-original-conversation
  acceptance to the existing runtime-acceptance OpenSpec change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=provider-neutral assistant replay;
  reuse=extend; change=modify; textual assistant dialogue uses the Easy Input
  Message string carrier instead of an incomplete output-message hybrid, while
  instruction, user, and tool content retains input grammar;
  facet:lifecycle=request,stream,release;
  facet:surface=listener,test,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Editing, truncating, compacting, migrating, or regenerating Codex session
  JSONL, SQLite, visible history, archives, pointers, or model metadata.
- Adding a DMXAPI-only retry or weakening fail-closed projection to hide a
  deterministic content-grammar error.
- Moving AIGW account, credential, route, storage-policy, or client-projection
  ownership into the proxy.
- Treating Superpowers plans, debug notes, or test workflow artifacts as a
  second specification or task authority beside this OpenSpec change.

## Impact

The change affects request-local projection in
`codex_dmx_proxy/listener/rewrite.py`, the bounded DMX compatibility projection
in `codex_dmx_proxy/compatibility/empty_response.py`, their focused regression
tests, the provider-portable Responses contract, and v1.0.44 release metadata.
It does not write Codex JSONL, SQLite, transcript history, or per-conversation
model metadata, and it does not change AIGW ownership or provider routing.
