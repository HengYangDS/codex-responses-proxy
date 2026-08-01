## Why

The repository was designed and named as though DMXAPI were the product,
although the runtime now serves DMXAPI, AIHubMix, UCloud, and future Responses
providers. That top-level category error propagated into the repository name,
Python package, environment namespace, installation paths, service identifiers,
documentation, tests, and signing commands. Host-specific signing defaults then
coupled publication to one maintainer's workstation.

Earlier projection tooling conflated accepted source with Forge targets and
rewrote provider-specific histories. The terminal design instead preserves one
collaborative signed commit graph and limits Forge operations to forward-only
publication plus Forge-native release tags. Expected child failures retain their
exit status without a Python traceback.

## What Changes

- Rename the product to **Codex Responses Proxy** (`codex-responses-proxy`) and
  make the Python, environment, runtime, service, documentation, and release
  namespaces provider-neutral.
- Keep `dmxapi`, `aihubmix`, and `ucloud` only where they identify real provider
  profiles or provider-specific wire behavior; adding a provider must not rename
  or restructure the product core.
- Make the provider manifest the extension SSOT: an ordinary provider is one
  table, while a special wire contract is at most one semantic policy module
  plus that table's policy declaration. Release inventory follows the same
  validated registry instead of maintaining another provider list.
- Make every third-party Responses request stateless: set `store=false` before
  upstream I/O and remove provider response, conversation, cache, stored-item,
  and item-ID bindings from the request copy.
- Replace provider-specific history rewriting with one forward-only collaborative
  commit graph; Forge publication only fast-forwards the same signed source.
- Replace personal signing defaults and local key paths with explicit,
  provider-scoped publication inputs backed by standard Git and OpenSSH.
- Remove the redundant signing runner rather than retaining a forwarding or
  compatibility layer.
- Publish the same accepted signed commit graph to both Forges without rewriting
  authorship, signatures, parent topology, or historical tags.
- Build one deterministic source archive and checksum manifest from immutable
  Git blobs, publish those exact assets on both Forges, and reject publication
  proof unless every asset digest matches across providers.
- Keep repository signing inputs external to product source and use the caller's
  existing standard OpenSSH agent; missing signing capability fails immediately.
- Extend the existing offline provider fixture and metadata contract instead of
  adding another projection wrapper or compatibility branch.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=provider projection source, signing authority, and failure diagnostics;
  reuse=extend; change=modify; preserve one signed source graph, publish targets
  forward-only, and keep expected runner failure traceback-free;
  facet:lifecycle=publication,validation;
  facet:surface=script,test,docs,openspec,trust-anchor;
  facet:authority=accepted-head,provider-main,provider-signature,claim,evidence.

## Out of Scope

- Moving accepted authority from `dev`, adding a compatibility alias, or
  rewriting commit history for Forge-specific identities.
- Rewriting `v1.0.45`, either Release, any existing provider-native tag, or
  historical evidence that truthfully records the former name.
- Changing Codex JSONL, SQLite, transcript history, or model metadata.
- Treating a local projection fixture as hosted CI or publication proof.

## Impact

Current product source, tests, CI, release tooling, Forge evidence readers,
documentation, and the existing `ci-diagnostics` evidence chain change. Hosted
publication and runtime installation remain separately verified lifecycle
transitions.
