# Design: Responses protocol integrity closeout

## Authority

`codex_responses_proxy.replay` owns provider-neutral request and response
projection. `transport` owns complete-body admission before downstream HTTP
commitment. `providers.registry` owns lexical provider route resolution from the
released manifest.

## Non-stream response transaction

For a successful non-SSE Responses exchange, transport reads at most eight MiB
before sending headers. An incomplete or oversized read is not successful even
when it carries partial bytes. The replay response projector then parses the
JSON, removes recognized provider ciphertext using the same recursive semantics
as SSE, rejects any unknown residual ciphertext carrier, and requires a
completed or incomplete Response object. Only the projected body is committed
downstream. Empty, malformed, truncated, oversized, or structurally unproved
bodies receive a bounded retryable local failure and cannot re-enter Codex
replay.

Non-Responses endpoints retain their existing streaming relay behavior.

## Request admission

All POST Responses bodies, including zero-length bodies, pass through the
existing fail-closed request projector. No upstream I/O occurs after a rejected
projection.

## Route grammar

Registry resolution accepts only an exact provider namespace followed by
`/v1/responses`, with an optional query. Encoded path material, dot segments,
duplicate separators, fragments, absolute URLs, and lookalike suffixes are
rejected locally.

## Compatibility

No provider policy is required for response projection. The registry exposes
one optional `WirePolicy` selected by a manifest name. It classifies exact
retryable upstream outcomes, supplies bounded retry and cooldown parameters,
and constructs the exhausted response. Core transport does not import or branch
on a provider name. A provider with no wire delta needs only a manifest entry.

Response-failed recovery reads a bounded structured error envelope. It does not
change request semantics because arbitrary message prose happens to contain a
known phrase.

## Provider backpressure

HTTP 429 is not a generic transient retry. The current upstream status, body,
and eligible headers are relayed after one call and without proxy sleep. The
transport records one absolute monotonic deadline under the selected provider's
collision-free key. Before remote I/O, Responses admission consults that shared
owner and returns local HTTP 429 while the provider remains in cooldown; another
provider is unaffected.

A valid delta-seconds or HTTP-date `Retry-After` determines the cooldown up to a
five-minute cap. Missing, invalid, zero, or expired values use the release-owned
five-second fallback. State is bounded, process-local, and cleared
by restart. The default Responses concurrency is 8 and remains configurable
through the validated runtime owner. This guardrail limits burst amplification;
it neither guesses nor encodes a provider's unpublished quota.

The product supports the Codex replay subset enumerated by source and tests.
New item carriers require a failing portability test and an explicit grammar
rule before admission; documentation must not call this subset the complete
OpenAI Responses protocol.

## Release and acceptance

Source proof requires Python 3.12, 3.13, and 3.14, Ruff, ty, architecture and
documentation gates, and statement plus branch coverage strictly above 95
percent. Completion additionally requires signed exact-tip GitLab and GitHub
CI, matching release assets and SHA-256 manifests, transactional installation,
DMXAPI/UCloud/AIHubMix runtime evidence, PyCharm MCP tool calls, and the same
original Codex conversation continuing across providers.
