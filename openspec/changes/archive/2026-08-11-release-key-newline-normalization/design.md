# Design

## Decision

The shared asset-signing boundary owns OpenSSH input normalization. It reads the
explicit key once, writes the same bytes with exactly one terminal newline into
a process-scoped temporary directory, sets mode `0600`, signs, and lets the
standard temporary-directory cleanup remove the copy.

## Alternatives rejected

| Alternative | Reason |
| --- | --- |
| Rewrite the GitLab variable | Couples correctness to one Forge's storage behavior. |
| Normalize in CI YAML | Duplicates policy outside the shared signing owner. |
| Accept an agent-only signer | Changes the existing explicit release-secret contract. |

## Safety

The normalized file is never committed, logged, returned, or retained. Existing
trust verification remains unchanged and still fails closed for a wrong key.
