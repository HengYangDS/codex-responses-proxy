## MODIFIED Requirements

### Requirement: Paired empty tool results remain explicit

A correctly paired function or custom-tool result whose exact output is the
empty string SHALL retain its call kind and `call_id` and SHALL use one stable
plaintext empty-result marker in the outbound request copy. The exception SHALL
NOT apply to ordinary dialogue, missing or null output, or an invalid pair. A
Codex-generated assistant placeholder consisting of exactly one valid, empty
`output_text` block SHALL be treated as non-semantic history and omitted rather
than forwarded or rejected.

#### Scenario: A paired tool result is textually empty

- **WHEN** a valid function or custom-tool output follows its matching call and
  its exact result is the empty string
- **THEN** the outbound request retains the pair with the fixed empty-result
  marker
- **AND** it is not rejected as an empty dialogue message.

#### Scenario: A replay contains an empty assistant placeholder

- **WHEN** Codex replay contains an assistant message whose content is exactly
  one valid `output_text` block with an empty string
- **THEN** the proxy omits that non-semantic item before upstream I/O
- **AND** preserves every later provider-portable item in order.

#### Scenario: Empty ordinary dialogue remains invalid

- **WHEN** a system, developer, user, or synthesized dialogue message contains
  no portable text, or an assistant message has any other empty shape
- **THEN** the proxy rejects the shape locally
- **AND** neither the empty-tool-result nor placeholder exception applies.
