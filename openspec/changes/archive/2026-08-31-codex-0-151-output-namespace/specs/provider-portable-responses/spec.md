## MODIFIED Requirements

### Requirement: Portable dialogue and tool relationships are preserved

The proxy SHALL preserve textual system, developer, user, and assistant
dialogue; agent author, recipient, and phase context; complete
function/custom-tool call-output pairs; and standalone cross-task tool delivery
results whose portable provenance is explicit. Assistant, synthesized-agent,
and standalone delivery history SHALL use provider-neutral Easy Input Message
strings. System, developer, user, and paired tool-output lists SHALL use
input-content grammar. Provider IDs, statuses, annotations, namespaces, and
opaque metadata SHALL NOT be required by a paired output's outbound form.

#### Scenario: Text and paired calls are replayed

- **WHEN** a request contains text messages, an agent message, a function call
  and output, and a custom-tool call and output
- **THEN** the upstream receives equivalent role-valid portable text and both
  complete call-output pairs
- **AND** every paired output retains the matching `call_id` and call kind.

#### Scenario: Namespaced function output is replayed

- **WHEN** a valid function output follows its matching call and carries the
  optional namespace metadata emitted by Codex
- **THEN** the upstream receives the complete provider-portable call-output pair
- **AND** the namespace metadata is not required or forwarded
- **AND** any other unproved output field is still rejected before upstream I/O.

#### Scenario: Standalone cross-task delivery is replayed

- **WHEN** Codex replays a standalone function output with a non-empty item ID,
  tool name, namespace, and visible output but no `call_id`
- **THEN** the upstream receives one provider-neutral assistant message that
  preserves the tool name, namespace, and visible output
- **AND** the proxy does not invent a function call, call identity, or
  provider-bound continuation.

#### Scenario: Assistant content is normalized for replay

- **WHEN** an assistant message or projected agent message contains
  `input_text`, `output_text`, or refusal content from stored history
- **THEN** its portable assistant representation uses a deterministic string
  that preserves the visible text and phase
- **AND** it does not require output-item ID, status, annotation, or typed
  output content from the prior provider.

#### Scenario: Instruction and user content remain input

- **WHEN** a system, developer, or user message contains typed text from stored
  history
- **THEN** its portable representation uses `input_text`
- **AND** no assistant-only output block is emitted for that role.

#### Scenario: An agent or tool output has only opaque ciphertext

- **WHEN** removing encrypted content would otherwise leave an agent message or
  tool output empty
- **THEN** the proxy inserts a stable plaintext omission marker using the
  assistant string carrier or tool-output input grammar
- **AND** it does not claim to have decrypted or reconstructed the omitted
  result.

#### Scenario: Classified DMX retry preserves the projected bytes

- **WHEN** the normal provider-portable request receives the exact classified
  DMX empty-response error
- **THEN** the proxy retries the current projected attempt bytes exactly once
- **AND** it does not rebuild replay, restore an older request body, or recreate
  a provider-bound assistant typed-block shape.

#### Scenario: Classified DMX retry retains replayable input images

- **WHEN** the normal portable request contains a validated remote
  `input_image` in system, developer, user, or tool-output input content and
  receives the exact classified DMX empty-response error
- **THEN** the byte-identical retry preserves that image on input grammar
- **AND** it does not turn valid non-text input into a local exhausted 503.

#### Scenario: Recovery contains non-text agent content

- **WHEN** a recoverable response contains valid non-text agent items
- **THEN** recovery preserves their provider-portable semantic representation
- **AND** does not fabricate text or require provider-bound identifiers.
