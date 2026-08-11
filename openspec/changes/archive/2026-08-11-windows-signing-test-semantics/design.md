# Design

## Decision

Express each platform contract once in the test inventory:

| Platform | Incomplete key expectation | Proof |
| --- | --- | --- |
| POSIX | Normalize one process-scoped copy and sign | Real OpenSSH integration test |
| Windows | Preserve provider-owned identity and fail closed | Focused mocked-platform regression |

The success test uses a pytest platform marker rather than emulating Windows
permissions or copying a provider-owned secret.

## Rejected alternatives

| Alternative | Reason |
| --- | --- |
| Make Windows accept the incomplete key | Reverses the security boundary already required by the canonical specification. |
| Rebuild Windows ACLs in tests or production | Duplicates operating-system policy and obscures the real contract. |
| Keep one cross-platform success assertion | Contradicts the intentional platform distinction. |
