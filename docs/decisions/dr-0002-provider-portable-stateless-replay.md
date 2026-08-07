# DR-0002: Keep Responses Replay Stateless and Provider-Portable

- Status: accepted
- Date: 2026-08-07

## Context

Third-party Responses providers do not share stored conversations, response or
item identifiers, encrypted reasoning state, or replay extensions. Reusing one
provider's continuation state after a route switch causes invalid requests and
can bind a client conversation to one upstream.

## Decision

Every outbound Responses request sets `store=false` and is rebuilt from one
closed provider-portable grammar. The projection removes provider-issued
response, conversation, cache, stored-item, search, replayed-reasoning, and
encrypted-content bindings while retaining portable dialogue and complete tool
relationships. Unknown or structurally unproved replay material fails locally.

Recovery consumes only the already-projected representation or a strictly
smaller derivation of it. No recovery path restores an earlier provider-bound
request, reads client conversation storage, or claims to decrypt ciphertext.

## Consequences

A conversation can switch among admitted providers without server-side state.
Continuity depends on client-replayed portable dialogue rather than a provider
store. The proxy may reject an input that lacks a proved portable meaning
instead of guessing or silently dropping a required tool relationship.

## Revisit Trigger

Revisit only if the Responses ecosystem adopts a provider-neutral,
cryptographically verifiable continuation format shared by every admitted
provider.
