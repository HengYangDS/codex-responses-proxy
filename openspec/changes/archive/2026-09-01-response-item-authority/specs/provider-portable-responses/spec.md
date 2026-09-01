## MODIFIED Requirements

### Requirement: Unproved replay shapes fail closed

Before upstream I/O, the proxy SHALL classify each Responses input item through
one authoritative item policy shared by diagnostics and provider-portable
projection. Malformed JSON, invalid input containers, genuinely unknown replay
item types, unknown content block types, orphaned or mismatched tool outputs,
duplicate call/output identities, and invalid required fields SHALL be rejected
locally. The error SHALL identify a bounded structural reason without returning
request text, credentials, or encrypted payloads.

#### Scenario: A future client introduces an unknown replay item

- **WHEN** the input list contains a replay item not recognized by the
  authoritative item policy
- **THEN** the proxy returns a local client error identified as an unknown item
- **AND** no configured provider receives the request.

#### Scenario: A recognized client item lacks portable semantics

- **WHEN** the authoritative policy recognizes an item emitted by a supported
  client but does not define a safe provider-portable projection for it
- **THEN** the proxy returns a local client error identified as bounded schema
  drift rather than an unknown item
- **AND** no configured provider receives the request.

#### Scenario: A tool output is not safely paired

- **WHEN** an output precedes its call, names an unknown `call_id`, duplicates
  an earlier output, or does not match the call kind
- **THEN** the request is rejected rather than silently deleting, reordering,
  or inventing tool history.

#### Scenario: Codex local shell history is provider-local

- **WHEN** replay contains a valid `local_shell_call` followed by its matching
  `function_call_output` and a current dialogue item
- **THEN** the proxy removes the complete local shell pair before upstream I/O
- **AND** it preserves the current dialogue item
- **AND** an incomplete or malformed local shell pair is rejected locally.

#### Scenario: Diagnostic and projection classification agree

- **WHEN** the proxy diagnoses and projects the same Responses input item
- **THEN** both operations consume the same authoritative item classification
- **AND** a recognized item cannot fall through projection as an unknown type.
