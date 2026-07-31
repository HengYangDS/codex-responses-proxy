## Context

The live `v1.0.44` process log records repeated `empty_text_content` projection
rejections after its current listener started. Earlier
`non_text_agent_content` fallback events belong to a predecessor process and
are not evidence of a current `v1.0.44` defect.

The normal projector already validates call/output pairing before projecting a
tool result. Its shared input-content function correctly rejects empty ordinary
text, but therefore cannot own the tool-only exception.

## Goals / Non-Goals

**Goals:**

- Preserve a valid empty tool result without weakening message validation.
- Keep the closed grammar, bounded retries, request-local mutation, and
  content-free operational evidence.
- Prove the complete release and runtime chain rather than only unit behavior.

**Non-Goals:**

- General coercion of empty, missing, null, or future output shapes.
- Decryption, reconstruction, or persistence of opaque provider state.
- Session-file repair or control-plane ownership changes.

## Decisions

### 1. The paired-output projector owns empty-result semantics

After call kind, `call_id`, caller, and encryption fields validate, an exact
empty-string output becomes `[tool returned no textual output]`. No shared
`allow_empty` flag is added: ordinary dialogue continues through the existing
strict content projectors.

### 2. Markers describe different facts

The empty-result marker states a known semantic fact. Existing opaque-content
markers state that provider state was omitted. They are not interchangeable;
neither claims decryption.

### 3. Completion is multi-plane

Local tests, coverage, OpenSpec, and ETHOS proof establish source readiness.
GitLab and GitHub establish independent signed histories, CI, tags, releases,
and tree parity. The installed released payload and unchanged live conversation
establish runtime continuity. The repository-family record only summarizes
fresh evidence after every preceding plane is complete.

## Risks / Trade-offs

- The empty marker adds words to an originally empty result. This is preferable
  to deleting the pair or weakening the grammar and is limited to a validated
  paired output.
- A future opaque block shape remains rejected until explicitly specified.
- Runtime success could be overstated from source proof; therefore installation
  and live continuity remain explicit later tasks.

## Migration Plan

1. Add focused failing tests for the observed shape and unchanged negative
   boundaries.
2. Implement the output-local projection rule and run focused plus full
   matrices.
3. Prepare, publish, and install the next signed patch release on both Forges.
4. Verify unchanged-conversation continuity and absence of the rejection,
   bounded-retry 503, traceback, and warnings.
5. Archive the Change, close the claim, supersede the premature `v1.0.42`
   record, and retire only owner-authorized represented lanes.

Rollback uses the existing protocol-v2 release transaction. It does not edit
conversation state.
