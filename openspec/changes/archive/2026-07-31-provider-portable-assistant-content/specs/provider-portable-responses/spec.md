## MODIFIED Requirements

### Requirement: Portable dialogue and tool relationships are preserved

The proxy SHALL preserve textual system, developer, user, and assistant
dialogue; agent author, recipient, and phase context; and complete
function/custom-tool call-output pairs. Textual assistant and synthesized-agent
history SHALL use the provider-neutral Easy Input Message string carrier rather
than an incomplete output-message object. System, developer, and user dialogue
and tool-output lists SHALL retain input-content grammar. Provider-issued item
IDs, statuses, annotations, and opaque internal metadata SHALL NOT be required
to preserve those relationships.

#### Scenario: Text and paired calls are replayed

- **WHEN** a request contains text messages, an agent message, a function call
  and output, and a custom-tool call and output
- **THEN** the upstream receives equivalent role-valid portable text and both
  complete call-output pairs
- **AND** every output retains the matching `call_id` and call kind.

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

#### Scenario: Classified DMX fallback retains role-valid content

- **WHEN** the normal provider-portable request receives the exact classified
  DMX empty-response error and the proxy performs its one bounded fallback
- **THEN** assistant, synthesized-agent, and opaque-reasoning dialogue retains
  the assistant string carrier while instruction, user, and tool-output content
  remains input content
- **AND** the fallback does not recreate the rejected assistant typed-block
  shape.

#### Scenario: Classified DMX fallback retains replayable input images

- **WHEN** the normal portable request contains a validated remote
  `input_image` in system, developer, user, or tool-output input content and
  receives the exact classified DMX empty-response error
- **THEN** the one bounded fallback preserves that image on input grammar
- **AND** it does not turn valid non-text input into a local exhausted 503.
