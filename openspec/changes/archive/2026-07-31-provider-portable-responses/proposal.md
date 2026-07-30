## Why

Codex replays provider-issued item identifiers and encrypted state through the
stable `aigw` provider identity, so changing AIGW accounts can send one
provider's opaque state to another and break the existing conversation. The
normal outbound path must become provider-portable before DMXAPI, UCloud/Azure,
and AIHubMix can be switched without editing stored Codex sessions.

## What Changes

- Add one provider-portable Responses projection that removes provider-bound
  continuation identifiers, stored-item references, reasoning state, and
  unreadable encrypted blocks before every upstream request.
- Preserve text dialogue, agent author/recipient/phase context, and complete
  function/custom-tool call-output pairs; use an explicit omission marker when
  an encrypted-only agent or tool output has no portable plaintext.
- Fail closed before upstream I/O for malformed or unknown replay item shapes
  instead of forwarding state whose portability cannot be proved.
- Route three canonical loopback namespaces to a fixed allowlist of HTTPS
  upstreams: DMXAPI, UCloud/Azure, and AIHubMix. Client requests cannot select
  an arbitrary upstream URL.
- Keep the exact DMX HTTP 477 recovery as a second-layer defense, scoped only
  to the DMXAPI route, and prevent its cooldown from blocking another provider.
- Sanitize streamed provider output so invalid reasoning, agent, or tool
  ciphertext is not reintroduced into later replay.
- Publish, install, and verify the change without modifying Codex JSONL,
  SQLite, transcript history, or per-conversation model metadata.

## Capabilities

### New Capabilities

- `provider-portable-responses`: subject=outbound and streamed Responses state;
  reuse=new; change=add; provides provider-neutral replay projection, fixed
  three-provider loopback routing, fail-closed validation, and route-scoped
  recovery; facet:lifecycle=request,stream,installation,release;
  facet:surface=listener,compatibility,test,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence

### Modified Capabilities

None.

## Out of Scope

- Editing, truncating, migrating, or regenerating Codex session JSONL, SQLite,
  visible history, archived conversations, or model metadata.
- Moving AIGW's ownership of accounts, credentials, current profile selection,
  storage policy, or transactional Codex/PyCharm/Air projection into the proxy.
- Treating Superpowers plans, debug notes, or test workflow artifacts as a
  second specification or task authority beside this OpenSpec change.
- Allowing downstream callers to submit an arbitrary upstream URL, host, or
  route-to-host mapping.

## Impact

The request rewrite, upstream transport, SSE rewrite, route-specific recovery,
tests, runtime documentation, release metadata, and acceptance evidence change
together. AIGW must project each Codex account to its corresponding loopback
namespace after the released proxy is installed; provider credentials continue
to arrive through the existing AIGW-managed client projection.
