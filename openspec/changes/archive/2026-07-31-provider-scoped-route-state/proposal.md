## Why

The provider-portable listener exposes `/dmxapi/v1`, `/ucloud/v1`, and
`/aihubmix/v1` as its canonical AIGW data-plane routes, while the reversible
route-state owner still derives every proxy endpoint from the older unscoped
`/v1` base. The current canonical AIGW DMXAPI endpoint is therefore healthy and
provider-scoped, but the installed schema-v2 state classifies it as `drifted`.
The same stale helper prevents `adopt-aigw` from recording the canonical route
and would make a later enable transition request the migration-only `/v1`
endpoint again.

This is a release-blocking integration defect in the untagged v1.0.44 source
train. It must be corrected before publication rather than hidden by editing
AIGW configuration, deleting route state, or weakening drift detection.

## What Changes

- Add a closed provider-route identity for `dmxapi`, `ucloud`, and `aihubmix`
  and derive each canonical AIGW loopback base from that identity.
- Advance newly written AIGW route state to schema v3, recording the AIGW
  account separately from its provider route and requiring the recorded proxy
  URL to equal the corresponding provider-scoped loopback base.
- Retain schema-v2 AIGW state only as bounded migration input. Use the existing
  `adopt-aigw` command as the sole owner-correct state migration entry after the
  canonical AIGW endpoint is already either the exact direct URL or the selected
  scoped proxy URL.
- Keep all AIGW endpoint mutations delegated to AIGW's public CLI and verify the
  canonical result; the proxy continues to never edit AIGW configuration.
- Preserve the unscoped `/v1` route only for the existing bounded direct-Codex
  compatibility mode and protocol-v2 migration ordering. New AIGW schema-v3
  state never records or emits it.
- Add focused RED-GREEN regression coverage for scoped adoption, schema-v2 to
  schema-v3 migration, exact direct restoration, provider allowlisting, and
  scoped custom-port discovery before changing production behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=provider-scoped AIGW route state;
  reuse=extend; change=modify; reversible AIGW control state becomes isomorphic
  with the three canonical provider namespaces while the unscoped DMX route is
  retained only for bounded direct-Codex compatibility and migration;
  facet:lifecycle=installation,migration,operation,release;
  facet:surface=route,control,test,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Editing AIGW's canonical configuration or any generated Codex, PyCharm, or Air
  projection directly instead of using AIGW's public CLI and sync lifecycle.
- Editing Codex JSONL, SQLite, transcript history, archives, pointers, or
  per-conversation model metadata.
- Removing the listener's bounded unscoped DMX migration route or changing its
  request-routing semantics in this patch.
- Turning proxy route control into a provider selector, credential owner, or
  replacement for AIGW account switching.
- Accepting arbitrary provider names, account-name inference, caller-supplied
  upstream hosts, or an unrelated endpoint as migration authority.
- Treating Superpowers plans, debugging notes, or test workflow artifacts as a
  second specification or task authority beside this OpenSpec change.

## Impact

The change affects reversible route-state validation and construction, installed
control adoption and toggling, source-side direct-route compatibility checks,
focused route/controller tests, canonical authority documentation, and the
pending v1.0.44 release record. It does not change listener upstream mappings,
request or stream projection, AIGW credentials, provider selection, or Codex
conversation storage.
