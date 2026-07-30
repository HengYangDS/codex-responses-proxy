## Context

See `proposal.md` for motivation. The installed `v1.0.42` listener rewrites
some reasoning state but deliberately preserves valid `agent_message`
ciphertext, sends every non-control path to one DMX upstream, and applies the
DMX empty-response cooldown before it knows which provider is intended. The
original Codex conversation uses the stable `aigw` provider key, while AIGW
changes the endpoint and client storage identity underneath that key.

The observed conversation contains provider-issued `rs_`, message, function,
custom-tool, and agent item IDs, plus encrypted reasoning and agent blocks.
UCloud/Azure needs Codex's stored-Responses behavior, but storage alone cannot
make another provider's IDs or ciphertext portable. The compatibility layer
must therefore operate on the normal request path, not only after DMX HTTP 477.

## Goals / Non-Goals

**Goals:**

- Define one deterministic, testable portable replay normal form.
- Keep route selection explicit and incapable of client-controlled SSRF.
- Preserve enough dialogue and tool structure for the same conversation to
  continue without pretending opaque provider state was decrypted.
- Retain exact, bounded provider recovery as defense in depth.
- Upgrade through the existing released-source and protocol-v2 lifecycle.

**Non-Goals:**

- Reconstructing hidden reasoning or encrypted tool/agent results.
- Making arbitrary third-party Responses endpoints dynamically configurable by
  request data.
- Moving profile, credential, storage, or Codex target ownership out of AIGW.
- Using session-file surgery as migration or rollback.

## Decisions

### 1. The normal outbound projection is the semantic owner

Every Responses request is reduced before the first network attempt. Repairing
only `store`, `previous_response_id`, HTTP 477, or a particular decrypt error
leaves another provider-bound carrier available, so those alternatives are
insufficient. Existing input-variant, response-failed, and DMX empty-response
fallbacks remain later layers and consume the already portable body.

### 2. Portable replay is a closed grammar for replay items

Top-level generation options remain extensible, but the `input` replay list is
closed because unknown item or content semantics can carry provider state.
The projection:

1. removes `previous_response_id`, `conversation`, `prompt_cache_key`, and the
   `reasoning.encrypted_content` include;
2. drops reasoning, stored-item reference, and stale provider-search items;
3. rebuilds messages, agent context, function/custom calls, and outputs from
   their portable fields, thereby removing item IDs, statuses, and internal
   metadata;
4. converts output-text blocks to input-text replay blocks;
5. removes encrypted blocks and inserts a stable omission marker only when a
   retained agent or output would otherwise be empty; and
6. validates call/output order, uniqueness, and type matching before
   serialization.

Agent messages are represented as assistant dialogue with a small structured
text header carrying author and recipient. Standard message replay is more
portable than forwarding a provider-specific agent item while retaining the
same information available to the model.

### 3. Unknown replay shapes are rejected locally

Passing unknown structures through was selected previously to avoid client
breakage, but it contradicts provider portability: the proxy cannot prove that
an unknown item is safe. The normalizer returns a bounded reason code; the HTTP
owner emits a local 400 without including request values. This preserves
privacy and makes client-version drift observable instead of silently sending
opaque state to a new provider.

### 4. Provider identity is carried by the path, not a header or body field

Canonical loopback bases are:

```text
http://127.0.0.1:8791/dmxapi/v1
http://127.0.0.1:8791/ucloud/v1
http://127.0.0.1:8791/aihubmix/v1
```

The listener maps only those namespaces to release-owned HTTPS upstream roots
and strips the provider prefix. It ignores no caller-supplied upstream header
because none is accepted. The existing unscoped `/v1` DMX path remains a
bounded migration route so protocol-v2 installation cannot cut off the live
conversation before AIGW sync; AIGW will not emit it after migration.

Release defaults bind the currently governed public endpoints. Environment
overrides are service-owner inputs, never downstream inputs, and are validated
as absolute HTTPS origins without credentials, query, or fragment before use.

### 5. Route identity is part of recovery policy

The exchange records the selected route. DMX HTTP 477 classification, fallback,
and cooldown run only for `dmxapi`; other routes relay 477 normally. The
cooldown check therefore cannot reject UCloud/Azure or AIHubMix after a DMX
failure with the same body. Generic transport and exact schema recovery remain
shared where their trigger does not assert DMX semantics.

### 6. Downstream stream sanitization prevents recurrence

Request projection is necessary even for old history, while SSE projection
prevents newly returned opaque agent/tool blocks from entering future history.
Rewrites are event-local and atomic: if an event cannot be parsed or safely
serialized, the exact original event is retained rather than emitting a partial
mutation. Reasoning ciphertext, encrypted content blocks, and encrypted-only
agent/tool content use the same portable omission rules as request replay.

### 7. OpenSpec is the only persistent change/task authority

This change folder owns proposal, design, spec, scope, and task state. TDD,
systematic debugging, and verification methods may guide execution, but they do
not create a parallel repository plan or specification surface.

## Risks / Trade-offs

- **Opaque history is less rich after projection** -> retain all portable text
  and complete tool pairs, use an explicit omission marker, and never imply the
  hidden value was recovered.
- **A future Codex item type is rejected** -> expose a bounded structural reason
  and add a spec/tested grammar extension before forwarding it.
- **Agent-message conversion changes presentation** -> preserve author,
  recipient, phase, and text in deterministic assistant dialogue rather than
  risk provider-specific item rejection.
- **A release default endpoint can drift** -> AIGW remains endpoint truth;
  changing a governed upstream requires a reviewed release/configuration
  update, not caller-controlled routing.
- **The migration-only unscoped DMX route can become residue** -> mark the three
  scoped routes canonical, configure all AIGW accounts to them, and retain no
  control-plane dependency on the unscoped route.

## Migration Plan

1. Complete RED-GREEN tests and all repository/OpenSpec/ETHOS gates in the
   isolated work lane.
2. Publish a signed patch release on both independent forge planes.
3. Install from the verified release through protocol-v2 handoff while the
   existing `/v1` DMX route remains accepted.
4. Publish the AIGW storage-policy change, then use AIGW's public CLI to project
   DMXAPI, UCloud/Azure, and AIHubMix to their three loopback bases across the
   global, PyCharm, and Air targets. Do not edit those files directly.
5. Verify the installed runtime identity, route behavior, account projection,
   and the unchanged original conversation through the full provider sequence.
6. Reverify PyCharm MCP initialization and tools listing.

If proxy installation fails before successor proof, the existing deployment
transaction restores the prior payload. If an AIGW projection fails, AIGW's
transaction restores its captured configuration state. Direct-provider
rollback is not considered a portability fix and must not be used to claim the
cross-provider acceptance succeeded.
