## Why

Codex can persist an assistant message containing one empty `output_text` block
as a control-plane placeholder. The proxy currently treats that no-op item as
empty dialogue and rejects the entire replay before upstream I/O, preventing an
otherwise valid conversation from continuing.

## What Changes

- Classify the exact empty Codex assistant placeholder as non-semantic history
  and omit it from the outbound request.
- Preserve every later portable item and keep all other empty or unproved
  dialogue shapes fail-closed.
- Add regression evidence for mixed history and all-empty input.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: distinguish a proven Codex-generated empty
  assistant placeholder from empty ordinary dialogue.

## Impact

The change is limited to Responses request projection and its protocol tests.
It does not alter Codex conversation storage, Provider routing, credentials,
native lifecycle, or the currently installed runtime before release.
