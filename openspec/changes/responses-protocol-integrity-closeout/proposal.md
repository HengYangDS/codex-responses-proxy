# Proposal: Responses protocol integrity closeout

## Why

The current provider-portable boundary sanitizes Responses requests and SSE
events, but successful non-stream JSON responses bypass that projection. Empty,
truncated, or malformed successful Responses bodies can also be committed as
success, empty request bodies bypass local validation, and provider routes accept
ambiguous suffixes outside the owned Responses endpoint.

## What changes

- Give replay response projection one provider-neutral JSON/SSE owner.
- Buffer successful non-stream Responses before downstream commitment, remove
  provider ciphertext, and fail closed on empty, truncated, malformed, or
  semantically incomplete success bodies.
- Reject empty Responses request bodies before upstream I/O.
- Resolve only normalized provider-scoped `/v1/responses` targets.
- Replace the DMX-named policy interface with one optional, narrow provider
  wire-policy contract; providers without a real wire difference remain
  manifest-only.
- Classify response-failed recovery from structured error fields rather than
  incidental prose and state the implemented Codex replay subset truthfully.
- Add behavior tests before implementation and retain ordinary non-Responses
  relay behavior.

## Boundaries

This change does not edit Codex JSONL, SQLite, transcript history, stored items,
conversation metadata, or model metadata. It does not add gateway routing,
budget, rate-limit, or control-plane responsibilities.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=Responses protocol integrity;
  reuse=extend; change=modify; close request, response, route, and provider
  wire-policy boundaries without taking ownership of Codex state;
  facet:lifecycle=request,response,recovery,release,acceptance;
  facet:surface=source,test,docs,openspec,ci,runtime;
  facet:authority=source,test,release,consumer.

## Out of Scope

- Editing Codex JSONL, SQLite, historical messages, archived conversations,
  Responses item records, model choices, or model metadata.
- Reading or writing AIGW configuration or credentials.
- Becoming a general routing, budgeting, rate-limit, or cluster gateway.
- Claiming a complete OpenAI Responses grammar beyond the replay subset proven
  by source and tests.
