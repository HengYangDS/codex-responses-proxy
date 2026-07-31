## Why

The released `v1.0.44` runtime still rejects a valid replay shape from the
unchanged Codex conversation: a correctly paired tool output whose exact result
is the empty string. It fails locally as `empty_text_content` before upstream
I/O, so repeated client attempts cannot resume the turn.

## What Changes

- Give only a correctly paired empty function/custom-tool result one explicit
  provider-portable plaintext representation.
- Keep empty dialogue, malformed ciphertext, unknown blocks, orphaned or
  mismatched calls, and all other unproved shapes fail-closed.
- Bind local proof, dual-Forge publication, installed-runtime continuity, log
  hygiene, and repository-family closeout as separate acceptance stages.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=empty paired tool results;
  reuse=extend; change=modify; provides the missing narrow replay projection
  without weakening ordinary dialogue or malformed-state rejection;
  facet:lifecycle=request,release,installation,acceptance;
  facet:surface=listener,test,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence

## Out of Scope

- Editing Codex JSONL, SQLite, transcript history, archives, resume pointers, or
  per-conversation model metadata.
- Treating empty dialogue, missing/null output, malformed encryption, or unknown
  replay structures as portable.
- Moving AIGW account, credential, endpoint, or provider-selection authority
  into this proxy.
- Replacing bounded retry and cooldown with unbounded retries.

## Impact

The request projector, focused regression tests, provider-portable
specification, release metadata, architecture prose, runtime acceptance, Forge
evidence, and final repository-family record are affected. No dependency or
public configuration surface is added.
