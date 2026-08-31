## Context

See [proposal.md](proposal.md). The observed Codex replay contains standalone
`function_call_output` delivery records with `id`, `name`, `namespace`, and
textual `output`, but no `call_id`. They represent cross-task messages rather
than the result half of an in-request function call.

## Goals / Non-Goals

**Goals:**

- Preserve the visible delivery as provider-neutral conversation input.
- Keep paired tool calls on the existing call/output path.
- Reject ambiguous hybrids and unknown fields before upstream I/O.

**Non-Goals:**

- Reading or rewriting Codex conversation storage.
- Inventing a call identity or forwarding Codex-specific metadata.
- Adding a provider-specific recovery branch.

## Decisions

Treat the exact standalone shape as a delivered assistant message. Its portable
text contains a deterministic JSON header with the tool name and namespace,
followed by the projected visible output. This reuses the existing message and
content grammar while preserving provenance that a plain output string would
lose.

An output with `call_id` remains governed by the existing paired-call rules.
An item without `call_id` is admitted only when it has a non-empty `id`, `name`,
and `namespace`, and no fields outside the closed standalone set. This avoids a
fallback that might reinterpret malformed paired outputs.

## Risks / Trade-offs

- **Future Codex delivery fields may differ** → fail closed until their semantics
  are observed and specified.
- **The provider sees a textual delivery rather than a tool result** → this is
  intentional because no portable call relationship exists to preserve.

## Migration Plan

Ship the request projection in the existing package, upgrade through the
transactional lifecycle, and retry the unchanged conversation. Rollback uses
the existing generation switch if the live replay does not recover.
