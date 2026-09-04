## Context

See [proposal.md](proposal.md). The request projector already owns all replay
normalization. The defect is one missing distinction inside that owner: Codex
persists a valid but non-semantic empty assistant placeholder, while the current
contract groups it with invalid empty dialogue.

## Goals / Non-Goals

**Goals:**

- Recognize only the observed placeholder shape.
- Remove it without changing the order or content of retained items.
- Keep every other empty or unproved structure fail-closed.

**Non-Goals:**

- Repair or rewrite Codex conversation storage.
- Accept arbitrary empty assistant content.
- Add a compatibility layer, provider branch, or dependency.

## Decisions

1. **Classify the placeholder at the message boundary.** The content projector
   remains strict. A dedicated predicate recognizes exactly one `output_text`
   block with an empty string and validates that the block has no unproved
   fields.
2. **Represent omission explicitly in the existing projection return type.** A
   `None` projected item means the validated source item carries no portable
   semantics. The input loop alone decides whether the final request still has
   usable input.
3. **Retain final empty-input rejection.** A request made solely of placeholders
   remains invalid as `empty_portable_input`; this prevents an empty upstream
   request and preserves fail-closed behavior.

## Risks / Trade-offs

- **A future empty shape could be semantically meaningful** → only the exact
  observed shape is omitted; every other shape remains rejected.
- **Dropping placeholders could erase the whole request** → the existing final
  non-empty input invariant remains authoritative.
