# DR-0002: Keep Responses Replay Stateless and Provider-Portable

- Status: accepted
- Date: 2026-08-07
- Last amended: 2026-09-23

## Context

Third-party Responses providers do not share stored conversations, response or
item identifiers, encrypted reasoning state, or replay extensions. Reusing one
provider's continuation state after a route switch causes invalid requests and
can bind a client conversation to one upstream.

## Decision

Every outbound Responses request sets `store=false` and is rebuilt from one
closed provider-portable grammar. The projection removes provider-issued
response, conversation, cache, stored-item, search and replayed-reasoning
bindings while retaining portable dialogue and complete tool relationships.
Required encrypted agent messages are native control data on the initial
attempt: preserve their original envelope and ciphertext so the producing
Provider can complete the current action. If the selected upstream explicitly
rejects that ciphertext as undecryptable, retry once with ciphertext removed,
visible content projected through the existing portable grammar, and an
omission marker where no plaintext survives. Unknown or structurally unproved
replay material fails locally.

Recovery consumes only the already-projected representation or a strictly
smaller derivation of it. No recovery path restores an earlier provider-bound
request, reads client conversation storage, or claims to decrypt ciphertext.
Generic shrinking recovery cannot discard encrypted agent messages. The exact
ciphertext-rejection recovery is a separate, single request-local projection.

## Consequences

A portable conversation can switch among admitted providers without server-side state.
Continuity depends on client-replayed portable dialogue rather than a provider
store. The proxy may reject an input that lacks a proved portable meaning
instead of guessing or silently dropping a required tool relationship.
Encrypted delegation first uses an upstream able to interpret its native
control payload. Cross-provider decryption is not assumed: an exact rejection
falls back to visible portable content, and an explicit omission marker records
any opaque-only portion that cannot be reconstructed.

This also preserves route mobility: switching Provider Accounts does not depend
on another provider's stored response or opaque item identifier.
Provider-specific recovery consumes the same portable owner or one bounded
derivation; it cannot become a parallel replay implementation.

## Revisit Trigger

Revisit when native control-message semantics change, or when the ecosystem
provides a documented interoperable encrypted transport. Require a real
sender-to-recipient content witness, not merely accepted JSON or a healthy listener.
