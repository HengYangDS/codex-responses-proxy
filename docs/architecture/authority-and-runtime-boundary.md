# Authority and Runtime Boundary

Status: canonical.

## Purpose

Codex DMX Proxy is a local data-plane adapter. It removes narrowly defined,
third-party-incompatible replay artifacts from outbound `/responses` requests.
It does not own conversation history, account credentials, provider routing
policy, or publication truth.

## Authority model

```text
Codex Desktop        -> per-conversation model selection and transcript state
AIGW CLI             -> marked provider configuration and multi-profile projection
GitLab + GitHub      -> independent signed tags, CI, and Release records
Released checkout    -> source admission and payload lifecycle composition
Installed control    -> read-only evidence, route control, same-payload reload
Listener             -> loopback Responses compatibility and handoff state
```

The proxy transforms requests only at the network edge. It must never repair a
conversation by mutating session JSONL, SQLite state, archives, or model
metadata. AIGW-owned marked provider blocks remain immutable to proxy route
commands.

The listener exposes three canonical data-plane namespaces:

```text
/dmxapi/v1  -> release-owned DMXAPI HTTPS origin
/ucloud/v1  -> release-owned UCloud/Azure HTTPS origin
/aihubmix/v1 -> release-owned AIHubMix HTTPS origin
```

AIGW selects one namespace through its account endpoint and supplies that
account's credential. The listener strips only the provider path prefix and
does not accept an upstream host from a request header or body. Environment
overrides are service-owner inputs and must be credential-free absolute HTTPS
origins.

Proxy-owned reversible AIGW route state mirrors that namespace explicitly.
Schema v3 records the AIGW account identifier separately from one closed
`dmxapi`, `ucloud`, or `aihubmix` provider route and requires `proxy_url` to be
the corresponding loopback base at the installed listener port. The unscoped
`/v1` URL remains only for the bounded direct-Codex compatibility path; it is
not a canonical AIGW endpoint and new AIGW state never records or emits it.

Historical schema-v2 AIGW state remains readable but cannot re-enable the
unscoped route. After AIGW's public CLI and sync lifecycle have projected the
selected account to either its exact direct URL or canonical scoped proxy URL,
installed `control.py adopt-aigw` is the sole proxy-state migration entry. It
atomically replaces only `install-state.json`, verifies the canonical AIGW
endpoint, and never edits AIGW configuration. Route-state migration therefore
follows successful released-payload installation and runtime proof; it is not
part of the payload transaction or its rollback authority.

Before remote I/O, `codex_dmx_proxy.listener.rewrite` projects Responses replay
onto a closed portable grammar. Provider continuation IDs, stored-item
references, reasoning/search state, provider item IDs, and opaque ciphertext
are removed. Text and complete call/output relationships remain. Unknown or
malformed replay fails locally; DMX HTTP 477 recovery and cooldown apply only
after that projection and only on the DMXAPI route. Stream sanitization prevents
new provider ciphertext from re-entering later replay.

The pure policy in `codex_dmx_proxy/compatibility/input_variant.py` owns the exact observed
Responses input-union failure. Transport orchestration may invoke that policy
once to construct a strictly smaller network request from the latest system,
developer, and user messages plus top-level instructions. No stored transcript
is rewritten, and the resulting attempt cannot cross into another retry or
reconnect policy.

## Released-source admission

Installation is permitted only after the source-side installer itself verifies
the provider-native signed GitLab and GitHub tags, required hosted CI jobs,
formal Release records, and common source tree. The evidence-only
`scripts/verify-publication-proof.py` exposes the same observation without
minting reusable authority. The installer requires a clean checkout before that
live observation; admission checks clean state again, then verifies that `HEAD`
is the exact signed annotated `v<VERSION>` tag under an external allowed-signers
anchor.

`codex_dmx_proxy.release.admission` reads immutable Git objects rather than
working-tree payload bytes and returns an opaque, immutable, one-use release
capability. That capability binds the tag object, commit, tree, dual-Forge
publication evidence, payload blobs and modes, aggregate serving-payload digest,
and canonical receipt. Before minting, admission compares the frozen `HEAD`, tag
object, tag commit, tree, and object format, requires clean state a final time,
and compares the same identity again. Dirty state or a clean ref move is rejected
rather than admitted. Git verification ignores global, system, and `GIT_*`
environment overrides, and disables replace objects, hooks, and filesystem
monitoring. A release archive, arbitrary directory, working-tree stage, or
installed controller cannot create that capability.

## Payload transaction and provenance

`codex_dmx_proxy.release.projection` owns the installed manifest schema,
integrity reader, exact historical inventories, and manifest-bounded purge. The
manifest covers only declared executable files and records release identity,
per-file digests, the canonical aggregate serving-payload digest, and the
release-receipt digest. `codex_dmx_proxy.release.transaction` consumes the
capability once and owns the private sibling transaction, exact rollback
snapshot, commit, installed-release state, and recovery-required journal while
composing projection writes. Configuration, backups, logs, request data,
credentials, and route state remain outside both owners.

The sibling transaction is private coordination state for the installer, not a
cryptographic evidence carrier. Its permissions isolate other local users; a
process already running as the same operating-system user is outside this
rollback-integrity threat boundary. Forge signatures, release admission, and the
installed manifest remain the authenticity evidence.

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

`control.py status --json` and portable `governance.py --json` are read-only
views of installed integrity, route authority, listener identity, transaction
state, and startup-frozen runtime identity. `codex_dmx_proxy` is the single
product root: `compatibility` owns pure provider recovery, `listener` owns the
serving process, `release` owns source and payload identity, `deployment` owns
release application, `route` owns reversible route state, and `supervision`
owns native user services. Package initializers are declarations, not facades.

## Lifecycle ownership

Installed `control.py reload` is same-payload only. It verifies the installed
manifest and receipt, prepares a non-accepting protocol-v2 child, stops the old
accept loop before `COMMIT`, and proves PID, transaction, release, aggregate
payload, receipt, manifest, and accepting state before `FINALIZE`. The listening
socket remains open. Accepted handlers drain to zero or the bounded lease; a
pre-finalize failure resumes old admission only after child exit is confirmed.
An unconfirmed abort fails closed.

A different release is installed only by source-side `install.py`. After release
admission and transaction commit, `codex_dmx_proxy.deployment.apply` uses the same
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

Uninstall keeps route restoration separate from destructive cleanup: drift or a
failed delegated restore preserves configuration, but does not by itself make
the later service-removal sequence atomic. Payload mutation begins only after
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
