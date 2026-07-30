## Context

The v1.0.43 normal outbound projector uses one content normalizer for dialogue
and tool output. That normalizer converts both `input_text` and `output_text`
to `input_text`. The unchanged original conversation then produced an
assistant message with an `input_text` block, which DMXAPI rejected at
`input[43].content[0]`. The same incorrect expectation exists in focused tests.

The classified DMX empty-response fallback has a second text projector with
the same role-agnostic conversion. Correcting only the normal outbound path
would therefore recreate invalid assistant `input_text` on the fallback retry.

Responses accepts historical assistant dialogue through two different unions:
the provider-neutral Easy Input Message accepts an assistant role with string
or input content, while a full output message requires provider-issued item
identity, status, and typed output content. Stripping those provider bindings
but retaining only `output_text` would create an incomplete hybrid. The repair
therefore uses the Easy Input Message string carrier for textual assistant
history and keeps function/custom-tool outputs on their input-content grammar.

## Goals / Non-Goals

**Goals:**

- Produce provider-neutral content for every projected dialogue message.
- Preserve that grammar through the bounded classified-empty-response retry.
- Preserve agent routing context, phase, plaintext, refusals, and omission
  markers without restoring provider ciphertext or item identifiers.
- Keep tool-output projection on its existing valid input-content grammar.

**Non-Goals:**

- Editing or compacting the original Codex conversation.
- Adding a provider-specific retry for a deterministic local projection bug.
- Reopening route isolation, storage policy, or encrypted-content ownership.

## Decisions

### 1. Textual assistant history uses the Easy Input Message string carrier

The dialogue projector accepts historical `input_text`, `output_text`, and
refusal blocks, but textual assistant messages are emitted as the assistant
Easy Input Message string form. This keeps phase while avoiding provider item
IDs, status, annotations, and typed output blocks. System, developer, and user
messages retain `input_text`; remote images remain input content. This fixes
the invalid request without inventing a new provider identity.

### 2. Synthesized agent messages use the same portable assistant carrier

Agent author/recipient headers, visible agent or refusal text, and
encrypted-only omission markers are combined deterministically into one
assistant string. The routing header remains explicit, but no provider output
item identity or ciphertext survives.

### 3. Tool outputs retain input-content blocks

Function and custom-tool output lists continue to use `input_text`; their API
grammar is distinct from assistant message output. The content helper therefore
receives an explicit target grammar rather than inferring one global rewrite.

### 4. Classified empty-response recovery preserves the same grammar

The DMX-only fallback projector will retain the same carrier: textual
assistant, synthesized-agent, and opaque-reasoning messages use assistant
strings; system, developer, user, and tool outputs use input content. Its policy
fingerprint version advances so prior cooldown keys cannot be confused with
the repaired retry semantics.

### 5. TDD reproduces the live rejected shape and retry regression

The first implementation step changes expectations to require the assistant
string carrier on both normal projection and classified fallback, and verifies
that the current code fails for the exact semantic reason. Production code
changes only after that RED result.

## Risks / Trade-offs

- **Third-party validators differ in union selection** -> emit the explicit
  assistant Easy Input Message string carrier instead of an incomplete typed
  output-message hybrid.
- **A broad helper change could alter tool outputs** -> tests independently
  assert dialogue and tool-output grammars.
- **A secondary fallback could regress the repaired request** -> transport
  tests inspect the actual second upstream body rather than trusting the
  fallback builder as their expected value.
- **A second release delays acceptance** -> retain v1.0.43 as the proven
  rollback runtime until v1.0.44 passes both Forge planes and protocol-v2
  installation.

## Migration Plan

1. Prove the current role-agnostic projection fails the new regression.
2. Implement the minimal role-aware projection and pass focused and full gates.
3. Archive and land the source-only change, publish v1.0.44 independently on
   GitLab and GitHub, and install it through protocol-v2.
4. Continue the unchanged original-conversation provider sequence from a fresh
   recorded prefix baseline; retain the failed v1.0.43 turn as historical
   evidence rather than rewriting it.
