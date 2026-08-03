# Authority and Runtime Boundary

Status: canonical.

## Purpose

Codex Responses Proxy is a local data-plane adapter. It removes narrowly defined,
third-party-incompatible replay artifacts from outbound `/responses` requests.
It does not own conversation history, account credentials, provider routing
policy, or publication truth.

## Authority model

```text
Codex Desktop        -> per-conversation model selection and transcript state
AIGW CLI             -> marked provider configuration and multi-profile projection
GitLab + GitHub      -> independent signed tags, CI, and Release records
Released checkout    -> source admission and payload lifecycle composition
Installed control    -> read-only evidence and same-payload reload
Listener             -> loopback Responses compatibility and handoff state
```

The proxy transforms requests only at the network edge. It must never repair a
conversation by mutating session JSONL, SQLite state, archives, or model
metadata. The proxy has no command that reads or changes AIGW or client
configuration.

The released provider manifest defines the listener's data-plane namespaces
and is the installed runtime's sole provider authority. Runtime environment
variables cannot replace it. The listener accepts only explicit
`POST /<provider>/v1/responses` routes and explicit read-only
`GET /<provider>/v1/models` routes; unscoped `/v1` has no implicit provider
meaning and unrelated provider endpoints are outside this product.
The current release declares:

```text
/dmxapi/v1/responses  -> release-owned DMXAPI Responses endpoint
/dmxapi/v1/models     -> release-owned DMXAPI model catalog endpoint
/ucloud/v1/responses  -> release-owned UCloud/Azure Responses endpoint
/ucloud/v1/models     -> release-owned UCloud/Azure model catalog endpoint
/aihubmix/v1/responses -> release-owned AIHubMix Responses endpoint
/aihubmix/v1/models    -> release-owned AIHubMix model catalog endpoint
```

A consumer selects one namespace through its own endpoint configuration and
supplies that account's credential. The listener strips only the selected
provider path prefix and does not accept an upstream host from a request header
or body. `codex_responses_proxy/providers/manifest.toml` is the single owner of
provider names, HTTPS origins, and optional wire-policy slugs. There is no
default route, installer-level upstream override, or parallel service variable.
Adding an ordinary provider is
one manifest table. A genuinely provider-specific wire extension adds one
module under `codex_responses_proxy/providers/policies/` and names it from that
table; the registry and release inventory contain no provider-name switch or
second policy list.

Only the Responses target enters replay projection, response projection,
Responses admission, cooldown, retry, and provider-specific recovery. A model
catalog target is a single transparent GET: it keeps client authentication,
uses the same manifest-owned upstream origin, and relays the upstream status,
eligible headers, and body without catalog parsing, filtering, or caching.

Before remote I/O, `codex_responses_proxy.replay.request` projects Responses
replay onto a closed portable grammar. `codex_responses_proxy.replay.response`
owns the matching provider-neutral output projection for both complete SSE
events and successful non-stream JSON. Non-stream transport buffers at most
eight MiB before commitment and admits only structurally proved `completed` or
`incomplete` Response documents with no unknown residual ciphertext; empty,
truncated, oversized, malformed, or non-terminal HTTP 2xx bodies fail locally
without committing partial bytes. The semantic
packages then separate runtime admission, telemetry, and safe logging from
transport route selection, bounded cooldown, upstream exchange, and downstream
HTTP/SSE relay; no mixed state or listener forwarding facade remains. Provider continuation IDs, stored-item
references, reasoning/search state, provider item IDs, and opaque ciphertext are
removed. Text and complete call/output relationships remain. A correctly
paired tool result whose exact value is the empty string is represented by one
fixed plaintext empty-result marker in the outbound request copy; ordinary
empty dialogue remains invalid. Unknown or malformed replay fails locally; DMX
HTTP 477 recovery and cooldown apply only after that projection and only on the
DMXAPI route. The optional `WirePolicy` contract contains that real provider
delta; ordinary providers need only one manifest table. Structured error type
and code fields, not incidental message prose, admit request-changing recovery.
Output projection prevents new provider ciphertext from re-entering later
replay.

The pure policy in `codex_responses_proxy/recovery/input_variant.py` owns the exact observed
Responses input-union failure. Transport orchestration may invoke that policy
once to construct a strictly smaller network request from the latest system,
developer, and user messages plus top-level instructions. No stored transcript
is rewritten, and the resulting attempt cannot cross into another retry or
reconnect policy.

## Released-source admission

Release governance verifies provider-native tags, hosted CI, formal Release
records, and common source tree independently of installation. The evidence-only
`tools/release/verify.py` owns that observation. The installer
consumes one selected release source, requires a clean checkout, and verifies
that `HEAD` is the exact signed annotated `v<VERSION>` tag under the caller's
external allowed-signers anchor.

`codex_responses_proxy.release.admission` reads immutable Git objects rather than
working-tree payload bytes and returns an opaque, immutable, one-use release
capability. That capability binds the tag object, commit, tree, payload blobs
and modes, aggregate serving-payload digest, and canonical receipt. Before
minting, admission compares the frozen `HEAD`, tag
object, tag commit, tree, and object format, requires clean state a final time,
and compares the same identity again. Dirty state or a clean ref move is rejected
rather than admitted. Git verification ignores global, system, and `GIT_*`
environment overrides, and disables replace objects, hooks, and filesystem
monitoring. A release archive, arbitrary directory, working-tree stage, or
installed controller cannot create that capability.

## Payload transaction and provenance

The payload package separates one lifecycle by reason to change:

- `inventory` owns the released and installed file sets;
- `projection` owns manifest integrity, exact historical inventories, and
  manifest-bounded purge;
- `candidate` validates and materializes one admitted candidate;
- `rollback` owns the exact prior-payload snapshot and restoration;
- `migration` removes only admitted retired privacy and executable residue;
- `state` persists the transaction journal and installed-release state;
- `transaction` coordinates those owners through the single-use state machine.

The manifest covers only declared executable files and records release identity,
per-file digests, the canonical aggregate serving-payload digest, and the
release-receipt digest. Configuration, backups, logs, request data, credentials,
and consumer endpoint state remain outside all payload owners.

The sibling transaction is private coordination state for the installer, not a
cryptographic evidence carrier. Its permissions isolate other local users; a
process already running as the same operating-system user is outside this
rollback-integrity threat boundary. The admitted signature, release receipt, and
installed manifest remain the installation authenticity evidence.

Cleanup follows the same ownership boundary. Exact retired raw-capture files are
deleted without being read and are never copied into rollback. Retired
install-owned executable paths are included in the prior-payload snapshot before
the candidate projection removes them, allowing a proven rollback to reconstruct
the exact previous owned projection without retaining obsolete paths on success.

A fresh installation or replacement finalizes only after one accepting listener
proves the expected release, aggregate serving-payload digest, receipt digest,
and manifest digest. A pre-finalize failure restores the exact prior owned
projection. If a committed handoff outcome cannot be proved, the transaction is
preserved as recovery-required rather than guessed successful or rolled back
blindly.

`python3 -m codex_responses_proxy.commands.control status --json` is the
read-only view of installed integrity, listener identity, transaction state, and
startup-frozen runtime identity. `codex_responses_proxy` is the single product
root:

- `commands` owns human-invoked lifecycle entrypoints;
- `runtime` owns portable paths, validated settings, admission, telemetry, and
  secret-safe logging;
- `providers` owns the provider manifest and true provider-specific wire deltas;
- `replay` owns the provider-neutral portable replay grammar;
- `recovery` owns provider-neutral request-local recovery policies;
- `transport` owns bounded cooldown, upstream exchange, and downstream HTTP/SSE relay;
- `listener` owns the serving process and socket handoff;
- `payload` owns installed identity, inventory, projection, and transactions;
- `release` owns signed source admission and publication observation;
- `deployment` owns application of an admitted payload; and
- `supervision` owns native user services and owned processes.

Package initializers are declarations, not facades.

Generic transport retries cover only the declared transient 5xx set. HTTP 429
is terminal for the current proxy attempt: transport records an absolute
deadline under a collision-free provider key and relays the first upstream
response. Runtime admission permits one active Responses exchange per registry
route and retains the configured global process bound across routes. A request
that waited for its route rechecks the same cooldown owner before remote I/O,
returns local 429 while the deadline remains, and never applies one provider's
state to another provider. A positive `Retry-After` is capped at five minutes;
absent, invalid, zero, or expired timing uses the release-owned five-second
fallback. Runtime configuration defaults global Responses concurrency to 8 as
a cross-route capacity guardrail, not as a claim about any provider's
undocumented quota.

## Lifecycle ownership

Installed `python3 -m codex_responses_proxy.commands.control reload` is
same-payload only. It verifies the installed manifest and receipt, prepares a non-accepting protocol-v2 child, stops the old
accept loop before `COMMIT`, and proves PID, transaction, release, aggregate
payload, receipt, manifest, and accepting state before `FINALIZE`. The listening
socket remains open. Accepted handlers drain to zero or the bounded lease; a
pre-finalize failure resumes old admission only after child exit is confirmed.
An unconfirmed abort fails closed.

A different release is installed only by source-side
`python3 -m codex_responses_proxy.commands.install`. After release admission and
transaction commit, `codex_responses_proxy.deployment.apply` uses the same
protocol-v2 handoff owner and runtime identity proof. Installed control exposes
no arbitrary stage-path upgrade or controller-only partial apply.

The sole compatibility exception is source-side replacement of a verified
listener that predates protocol-v2 handoff. It requires explicit
`--allow-legacy-bootstrap` authorization and a bounded zero-active quiet window
on the same PID before payload mutation. The historical verifier shared with
rollback and purge proves the schema-specific inventory and derives the retired
entrypoint used by listener discovery, quiet-window rechecks, and termination.
After candidate commit, native supervision is replaced before successor proof
so no service retains the old entrypoint. `--force-legacy-bootstrap` is separate
interruption authorization; it skips only the quiet wait, never manifest,
entrypoint, PID, or rollback proof. Neither flag applies to same-payload reload
or a current protocol-v2 listener. A failure after old-process exit restores the
old owned projection, reinstalls supervision with the historical entrypoint, and
must prove one accepting historical listener; otherwise rollback is explicitly
reported as failed.

Uninstall never reads or changes consumer configuration. Payload mutation begins only after
the native service reports `absent` and exact owned watchdog and listener
processes are proved gone. Ownership requires a Python command whose resolved
`argv[1]` equals the installed script; identity is re-read before signalling and
boundedly rechecked afterwards so PID reuse cannot target a new occupant.
`--purge` removes only a valid current manifest inventory or an exact supported
historical inventory. Unknown physical content is preserved and reported as an
incomplete uninstall.

## Diagnostic boundary

Runtime status contains only bounded counters, classifications, provenance
digests, and timestamps. Logs are a secondary local diagnostic surface:
structured events are bounded by rotating retention and redact secret-shaped
values. No raw request, response, header, prompt, query value, credential, or
upstream error payload is retained. Retired raw-capture filenames are removed
without reading their contents; oversized legacy log segments are discarded
rather than copied into evidence. Native service stdout and stderr must not form
an unbounded parallel log channel.

Input-union diagnostics contain closed-enum type counts, call/output pairing
state, the first detected incompatibility category, and a hash of a capped
categorical shape. Unknown names, values, and exact collection cardinalities
are erased before hashing or diagnostic logging. Recovery events may retain
exact byte lengths and retained or dropped item counts, but never the
corresponding message values or unknown names.
